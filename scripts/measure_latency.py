"""Latency harness for the CURRENT /evaluate path (slice 1 baseline).

Hits POST /evaluate in-process via fastapi.testclient.TestClient(src.api.app).
TestClient as a context manager runs the app lifespan, which builds
EvaluationPipeline(enable_prongs=[1, 2, 3, 4]) — no uvicorn, no network
server, no vLLM.

Per timed run we record:
  - wall-clock ms of the HTTP call (time.perf_counter around client.post)
  - each prong's processing_time from the JSON response
    (prong_results[].processing_time is SECONDS — time.time() deltas in
    src/prongs/*.py — and is converted to ms here)

Outputs:
  evaluation_results/latency_baseline.json  (machine-readable)
  evaluation_results/latency_baseline.md    (human table)

Any quantity that was not measured is written as "unmeasured".
/generate-and-evaluate is deliberately NOT measured here (needs vLLM).

Run from the repo root:
    .venv/bin/python scripts/measure_latency.py
"""

import json
import os
import platform
import re
import socket
import statistics
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PROMPT = "What is the capital of France?"
TEXT = "The capital of France is Paris, in the north of the country."
LANGUAGE = "en"
N_WARM = 2
N_TIMED = 5
UNMEASURED = "unmeasured"

PRONG_KEYS = ["Prong 1", "Prong 2", "Prong 3", "Prong 4"]


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or UNMEASURED


def mem_total_gb() -> str:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 2)
    except (OSError, ValueError, IndexError):
        pass
    return UNMEASURED


def hardware_fingerprint() -> dict:
    hw = {
        "hostname": socket.gethostname(),
        "cpu_model": cpu_model(),
        "nproc": os.cpu_count(),
        "mem_total_gb": mem_total_gb(),
        "python_version": platform.python_version(),
    }
    try:
        import torch
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cuda = torch.cuda.is_available()
        hw["torch_version"] = torch.__version__
        hw["cuda_available"] = cuda
        if caught:
            hw["cuda_note"] = str(caught[0].message)
        if not cuda:
            hw["compute"] = "CPU-only (CUDA init failed; torch built with CUDA, driver too old)"
        else:
            hw["compute"] = "CUDA"
    except ImportError:
        hw["torch_version"] = UNMEASURED
        hw["cuda_available"] = UNMEASURED
        hw["compute"] = "torch not installed"
    return hw


def summarize(values):
    """n/mean/std/min/max over measured values; 'unmeasured' if none."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return {
            "n": 0,
            "mean": UNMEASURED,
            "std": UNMEASURED,
            "min": UNMEASURED,
            "max": UNMEASURED,
        }
    return {
        "n": len(vals),
        "mean": round(statistics.fmean(vals), 3),
        "std": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
    }


def git_ref() -> str:
    import subprocess
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()[:7]
        if branch and commit:
            return f"{branch} @ {commit}"
    except Exception:
        pass
    return UNMEASURED


def run(client):
    """One POST /evaluate. Returns (status, wall_ms, per_prong_ms, total_time_ms)."""
    start = time.perf_counter()
    resp = client.post(
        "/evaluate",
        json={"prompt": PROMPT, "text": TEXT, "language": LANGUAGE},
    )
    wall_ms = (time.perf_counter() - start) * 1000.0
    if resp.status_code != 200:
        return resp.status_code, wall_ms, {}, UNMEASURED

    data = resp.json()
    per_prong_ms = {}
    for prong in data.get("prong_results", []):
        name = prong.get("prong_name", "")
        for key in PRONG_KEYS:
            if name.endswith(f"({key})") or name == key:
                pt = prong.get("processing_time")
                if isinstance(pt, (int, float)):
                    per_prong_ms[key] = pt * 1000.0  # seconds -> ms
                break
    agg = data.get("aggregated_scores", {}).get("metadata", {}).get("total_time")
    total_time_ms = agg * 1000.0 if isinstance(agg, (int, float)) else UNMEASURED
    return resp.status_code, wall_ms, per_prong_ms, total_time_ms


def fmt(value) -> str:
    return UNMEASURED if value == UNMEASURED else f"{value:.1f}"


def main():
    from fastapi.testclient import TestClient
    from src.api import app

    hw = hardware_fingerprint()
    warmup_wall = []
    runs = []

    with TestClient(app) as client:
        for i in range(N_WARM):
            status, wall, per_prong, total = run(client)
            warmup_wall.append(wall)
            print(f"warmup {i + 1}/{N_WARM}: status={status} wall={wall:.1f} ms "
                  f"prongs={ {k: round(v, 1) for k, v in per_prong.items()} }")
            if status != 200:
                print("warmup failed; aborting — cannot trust subsequent numbers",
                      file=sys.stderr)
                sys.exit(1)

        for i in range(N_TIMED):
            status, wall, per_prong, total = run(client)
            runs.append({
                "run": i + 1,
                "status": status,
                "wall_clock_ms": round(wall, 3),
                "prong_ms": {k: (round(v, 3) if isinstance(v, (int, float)) else UNMEASURED)
                             for k, v in per_prong.items()},
                "total_prong_sum_ms": (round(sum(per_prong.values()), 3)
                                       if per_prong else UNMEASURED),
                "aggregated_total_time_ms": (round(total, 3)
                                             if isinstance(total, (int, float)) else UNMEASURED),
            })
            print(f"timed  {i + 1}/{N_TIMED}: status={status} wall={wall:.1f} ms "
                  f"prongs={ {k: round(v, 1) for k, v in per_prong.items()} }")

    def prong_key_values(key):
        out = []
        for r in runs:
            if r["status"] != 200:
                out.append(UNMEASURED)
                continue
            out.append(r["prong_ms"].get(key, UNMEASURED))
        return out

    result = {
        "meta": {
            "path": "/evaluate",
            "method": "POST",
            "transport": "fastapi.testclient.TestClient(src.api.app), in-process "
                         "(no uvicorn, no TCP; lifespan built EvaluationPipeline)",
            "request": {"prompt": PROMPT, "text": TEXT, "language": LANGUAGE},
            "n_warmup": N_WARM,
            "n_timed": N_TIMED,
            "std_definition": "sample std (n-1)",
            "units": {
                "wall_clock_ms": "wall clock around client.post",
                "prong_ms": "prong_results[].processing_time from JSON "
                             "(seconds, time.time() deltas) x 1000",
            },
            "git": git_ref(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "not_measured": [
                "/generate-and-evaluate (needs a vLLM generation server — out of slice 1)",
            ],
        },
        "hardware": hw,
        "warmup_wall_clock_ms": [round(w, 3) for w in warmup_wall],
        "wall_clock_http_ms": {
            "per_run_ms": [r["wall_clock_ms"] for r in runs],
            **summarize([r["wall_clock_ms"] for r in runs]),
        },
        "prongs": {},
        "total_ms": {},
        "runs": runs,
    }

    prong_labels = {
        "Prong 1": "LLM-as-Judge (Prong 1)",
        "Prong 2": "Rule-Based (Prong 2)",
        "Prong 3": "Extraction-Based (Prong 3)",
        "Prong 4": "Intrinsic (Prong 4)",
    }
    for key in PRONG_KEYS:
        vals = prong_key_values(key)
        result["prongs"][key] = {
            "response_name": prong_labels[key],
            "per_run_ms": vals,
            **summarize(vals),
        }

    sum_vals = [r["total_prong_sum_ms"] for r in runs]
    agg_vals = [r["aggregated_total_time_ms"] for r in runs]
    result["total_ms"] = {
        "sum_of_prongs": {
            "per_run_ms": sum_vals,
            **summarize(sum_vals),
        },
        "aggregated_metadata_total_time": {
            "per_run_ms": agg_vals,
            **summarize(agg_vals),
        },
        "note": "aggregated_scores.metadata.total_time is the pipeline's own "
                "sum of prong processing times; wall clock includes HTTP/ASGI "
                "dispatch overhead on top.",
    }

    out_dir = REPO_ROOT / "evaluation_results"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "latency_baseline.json"
    md_path = out_dir / "latency_baseline.md"

    json_path.write_text(json.dumps(result, indent=2) + "\n")

    lines = []
    lines.append("# Latency baseline — `/evaluate` (slice 1, current system)")
    lines.append("")
    lines.append(f"- Path: `POST /evaluate` via `fastapi.testclient.TestClient(src.api.app)` "
                 f"(in-process; no uvicorn, no TCP)")
    lines.append(f"- Request: prompt={PROMPT!r}, text={TEXT!r}, language=`{LANGUAGE}`")
    lines.append(f"- Runs: {N_WARM} warmup (discarded), {N_TIMED} timed")
    lines.append(f"- git: `{result['meta']['git']}`")
    lines.append(f"- Timestamp (UTC): {result['meta']['timestamp_utc']}")
    lines.append("")
    lines.append(f"Hardware: `{hw['hostname']}` — {hw['cpu_model']}, "
                 f"{hw['nproc']} CPUs, {hw['mem_total_gb']} GB RAM, "
                 f"Python {hw['python_version']}, torch {hw['torch_version']}, "
                 f"CUDA available={hw['cuda_available']} → {hw['compute']}")
    if hw.get("cuda_note"):
        lines.append(f"- CUDA note: {hw['cuda_note']}")
    lines.append(f"- Warmup wall clock (discarded, context only): "
                 f"{[round(w, 1) for w in warmup_wall]} ms")
    lines.append("")
    lines.append("## Latency (timed runs, ms)")
    lines.append("")
    lines.append("| Metric | n | mean | std | min | max |")
    lines.append("|---|---|---|---|---|---|")

    def row(label, s):
        return f"| {label} | {s['n']} | {fmt(s['mean'])} | {fmt(s['std'])} | " \
               f"{fmt(s['min'])} | {fmt(s['max'])} |"

    lines.append(row("HTTP /evaluate wall clock", result["wall_clock_http_ms"]))
    for key in PRONG_KEYS:
        lines.append(row(f"{prong_labels[key]} processing_time", result["prongs"][key]))
    lines.append(row("Sum of prong processing times", result["total_ms"]["sum_of_prongs"]))
    lines.append(row("aggregated_scores.metadata.total_time",
                     result["total_ms"]["aggregated_metadata_total_time"]))
    lines.append("")
    lines.append("prong `processing_time` is reported by the pipeline in seconds "
                 "(time.time() deltas); converted to ms (x1000) above.")
    lines.append("")
    lines.append("Note: on `/evaluate` there is no vLLM `intrinsic_data`, so Prong 4 "
                 "returns its Phase-1 neutral placeholders (its processing_time is "
                 "trivially ~0 ms); Prong 4 real-logit latency is measured only via "
                 "the generation paths.")
    lines.append("")
    lines.append("## Not measured (this slice)")
    lines.append("")
    for item in result["meta"]["not_measured"]:
        lines.append(f"- {item}")
    missing = []
    for key in PRONG_KEYS:
        for v in result["prongs"][key]["per_run_ms"]:
            if v == UNMEASURED:
                missing.append(key)
                break
    for m in sorted(set(missing)):
        lines.append(f"- {prong_labels[m]} processing_time (prong missing or errored in response)")
    if not missing:
        lines.append("- (none — all four prongs returned processing_time in every timed run)")
    lines.append("")
    md_path.write_text("\n".join(lines))

    print(f"\nwrote {json_path}\nwrote {md_path}")


if __name__ == "__main__":
    main()
