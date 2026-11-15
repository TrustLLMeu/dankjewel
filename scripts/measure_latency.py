"""Latency harness — CURRENT /evaluate, every shipped track (Phase 4).

Hits POST /evaluate in-process via fastapi.testclient.TestClient(src.api.app).
TestClient as a context manager runs the app lifespan, which builds
EvaluationPipeline(enable_prongs=[1, 2, 3, 4]) — no uvicorn, no TCP, no vLLM.

What this measures (slice: "measure the CURRENT system"):
  1. Per-track /evaluate wall-clock, COLD + WARM.
       - cold  = the first call in a FRESH process (includes every model load
         that track triggers; this is what a cold user's first request pays)
       - warm  = the 5 steady-state calls after the cold one
     Tracks (all on the same tiny English prompt unless noted):
       baseline     all flags off
       tiny_judge   tiny_judge=True            (0.5B judge on Prong 1 Relevance)
       llm_extract  llm_extract=True           (1.5B claims on Prong 3)
       llm_verify   llm_verify=True            (MiniCheck NLI on Prong 3, KB-unknown claims)
       all          all three on
       verifier_engaged  llm_verify=True on a text whose claims are KB-unknown,
                         so the MiniCheck verifier actually fires end-to-end
                         (the plain Paris text is fully KB-confirmed, so the
                         verifier does NOT run there).
     Each track runs in its OWN subprocess so the cold load is genuine (models
     are not pre-warmed by a prior track in the same process).
  2. Direct model-call timings (1 cold + 20 warm):
       judge     127.0.0.1:18092  Qwen/Qwen2.5-0.5B-Instruct  (chat completion)
       claims    127.0.0.1:18093  Qwen/Qwen2.5-1.5B-Instruct  (one paragraph)
       verifier  MiniCheck-Flan-T5-Large (one claim vs one KB fact doc; the
                 cold call includes the one-time model load)
  3. Hardware fingerprint.

Outputs:
  evaluation_results/latency_baseline.json  (machine-readable)
  evaluation_results/latency_baseline.md    (human table)

Any quantity that was not measured is written as "unmeasured".
/generate-and-evaluate is deliberately NOT measured (needs a vLLM generation
server with logprobs — out of scope).

The judge/claims HTTP keys are read from the environment (DANKJEWEL_JUDGE_API_KEY),
never hardcoded. Run with that env var set.

Run from the repo root:
    DANKJEWEL_JUDGE_API_KEY=... .venv/bin/python scripts/measure_latency.py
"""

import json
import os
import platform
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
# A text whose extracted claims are KB-UNKNOWN (population/size), so the
# MiniCheck verifier actually scores against the subject's KB facts.
VERIFIER_ENGAGED_TEXT = "Paris has a population of two million people."
LANGUAGE = "en"
N_WARM = 5          # warm /evaluate calls per track
N_MODEL_WARM = 20   # warm direct model calls per model
UNMEASURED = "unmeasured"

PRONG_KEYS = ["Prong 1", "Prong 2", "Prong 3", "Prong 4"]

TRACKS = {
    "baseline":       dict(tiny_judge=False, llm_extract=False, llm_verify=False),
    "tiny_judge":     dict(tiny_judge=True,  llm_extract=False, llm_verify=False),
    "llm_extract":    dict(tiny_judge=False, llm_extract=True,  llm_verify=False),
    "llm_verify":     dict(tiny_judge=False, llm_extract=False, llm_verify=True),
    "all":            dict(tiny_judge=True,  llm_extract=True,  llm_verify=True),
}
TRACK_ORDER = ["baseline", "tiny_judge", "llm_extract", "llm_verify", "all"]
TRACK_LABELS = {
    "baseline": "baseline (all flags off)",
    "tiny_judge": "tiny_judge only (0.5B judge)",
    "llm_extract": "llm_extract only (1.5B claims)",
    "llm_verify": "llm_verify only (MiniCheck NLI)",
    "all": "all three on",
}


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or UNMEASURED


def mem_total_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 2)
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


def percentile(values, q):
    """Linear-interpolation percentile (numpy 'linear' default). None if empty."""
    vals = sorted(v for v in values if isinstance(v, (int, float)))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * q
    lo, hi = int(rank), min(int(rank) + 1, len(vals) - 1)
    frac = rank - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


def summarize(values, unit="ms"):
    """n/median/p95/mean/std/min/max; 'unmeasured' for the stats if none."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return {"n": 0, "median": UNMEASURED, "p95": UNMEASURED, "mean": UNMEASURED,
                "std": UNMEASURED, "min": UNMEASURED, "max": UNMEASURED}
    return {
        "n": len(vals),
        "median": round(statistics.median(vals), 3),
        "p95": round(percentile(vals, 0.95), 3),
        "mean": round(statistics.fmean(vals), 3),
        "std": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0,
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
    }


def git_ref() -> str:
    import subprocess
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                cwd=REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        commit = subprocess.run(["git", "rev-parse", "HEAD"],
                                cwd=REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()[:7]
        if branch and commit:
            return f"{branch} @ {commit}"
    except Exception:
        pass
    return UNMEASURED


def extract_call(resp_json: dict) -> dict:
    """Pull the per-prong processing times + the metadata timings the API
    already reports out of one /evaluate response."""
    out = {
        "prong_ms": {},
        "relevance_llm_ms": None,          # tiny_judge track (Prong 1 Relevance)
        "factual_verification_ms": None,    # Prong 3 FactualAccuracy
        "relation_counts": None,
        "num_claims": None,
        "verifier_scores": [],
        "verifier_errors": None,
    }
    for p in resp_json.get("prong_results", []):
        name = p.get("prong_name", "")
        pt = p.get("processing_time")
        for key in PRONG_KEYS:
            if name.endswith(f"({key})") or name == key:
                if isinstance(pt, (int, float)):
                    out["prong_ms"][key] = round(pt * 1000, 3)  # seconds -> ms
                break
        for dim in p.get("dimensions", []):
            meta = dim.get("metadata") or {}
            dname = dim.get("name")
            if dname == "Relevance" and "llm_processing_time_ms" in meta:
                out["relevance_llm_ms"] = meta.get("llm_processing_time_ms")
            if dname == "Factual Accuracy":
                out["factual_verification_ms"] = meta.get("verification_time_ms")
                out["relation_counts"] = meta.get("relation_counts")
                out["num_claims"] = meta.get("num_claims")
                if "verifier_errors" in meta:
                    out["verifier_errors"] = meta.get("verifier_errors")
                for cd in meta.get("claim_details", []):
                    if isinstance(cd, dict) and "verifier_score" in cd:
                        out["verifier_scores"].append(cd["verifier_score"])
    return out


def run_track(flags: dict, text: str = TEXT, n_warm: int = N_WARM) -> dict:
    """1 cold + n_warm warm POST /evaluate calls on this process's pipeline.

    Intended to run in a FRESH process (one per track) so the cold call
    includes that track's real model loads.
    """
    from fastapi.testclient import TestClient
    from src.api import app
    with TestClient(app) as c:
        runs = []
        for i in range(1 + n_warm):
            body = {"prompt": PROMPT, "text": text, "language": LANGUAGE, **flags}
            t0 = time.perf_counter()
            r = c.post("/evaluate", json=body)
            wall = (time.perf_counter() - t0) * 1000.0
            rec = {"run": i + 1, "cold": i == 0, "status": r.status_code,
                   "wall_ms": round(wall, 3)}
            if r.status_code == 200:
                rec.update(extract_call(r.json()))
            runs.append(rec)
        return {
            "flags": flags,
            "text": text,
            "n_warm": n_warm,
            "cold_ms": runs[0]["wall_ms"],
            "warm_ms": [x["wall_ms"] for x in runs[1:] if x["status"] == 200],
            "runs": runs,
        }


def direct_model_timings(n_warm: int = N_MODEL_WARM) -> dict:
    """Direct timings of the three underlying models: 1 cold + n_warm warm."""
    out = {}
    try:
        from src.llm_judge_client import LLMJudgeClient
        client = LLMJudgeClient()  # reads DANKJEWEL_JUDGE_API_KEY from env

        # judge (0.5B) — one chat completion
        t0 = time.perf_counter(); client.judge(PROMPT, TEXT); jc = (time.perf_counter() - t0) * 1000
        jt = []
        for _ in range(n_warm):
            t0 = time.perf_counter(); client.judge(PROMPT, TEXT); jt.append((time.perf_counter() - t0) * 1000)
        out["judge"] = {
            "endpoint": "http://127.0.0.1:18092/v1/chat/completions",
            "model": client.model_name,
            "cold_ms": round(jc, 3),
            "warm_ms": [round(x, 3) for x in jt],
        }

        # claims (1.5B) — one paragraph
        t0 = time.perf_counter(); client.claims(TEXT); cc = (time.perf_counter() - t0) * 1000
        ct = []
        for _ in range(n_warm):
            t0 = time.perf_counter(); client.claims(TEXT); ct.append((time.perf_counter() - t0) * 1000)
        out["claims"] = {
            "endpoint": "http://127.0.0.1:18093/v1/chat/completions",
            "model": client.claims_model_name,
            "cold_ms": round(cc, 3),
            "warm_ms": [round(x, 3) for x in ct],
        }
        client.close()
    except Exception as e:
        out["_llm_error"] = f"{type(e).__name__}: {e}"

    # verifier (MiniCheck) — direct, one claim vs one KB fact doc
    try:
        from src.resources.nli_verifier import NliVerifier
        from src.resources.wikidata_offline import OfflineWikidata
        wd = OfflineWikidata()
        qid = wd.lookup_entity("Paris")
        doc = wd.format_entity_facts(qid) if qid else "France is a country in Europe."
        claim = VERIFIER_ENGAGED_TEXT
        v = NliVerifier()
        t0 = time.perf_counter(); p = v.score(claim, doc); vc = (time.perf_counter() - t0) * 1000
        vt = []
        for _ in range(n_warm):
            t0 = time.perf_counter(); v.score(claim, doc); vt.append((time.perf_counter() - t0) * 1000)
        out["verifier"] = {
            "model": v.model_name,
            "claim": claim,
            "doc": doc,
            "sample_support_prob": round(float(p), 4),
            "cold_ms_includes_load": round(vc, 3),
            "warm_ms": [round(x, 3) for x in vt],
        }
    except Exception as e:
        out["_verifier_error"] = f"{type(e).__name__}: {e}"
    return out


# ── worker mode: one track in this (fresh) process ─────────────────────────

def _worker(track: str, out_path: str, text: str):
    flags = TRACKS[track]
    result = run_track(flags, text=text)
    Path(out_path).write_text(json.dumps(result, indent=2))


# ── parent mode: orchestrate ────────────────────────────────────────────────

def _spawn_track(track: str, text: str = TEXT) -> dict:
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name
    log_path = out_path + ".log"
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--track", track, "--out", out_path, "--text", text],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
        )
        with open(log_path, "w") as f:
            f.write(proc.stderr or "")
        try:
            return json.loads(Path(out_path).read_text())
        except Exception as e:
            return {"error": f"track {track} failed: {e}",
                    "stderr_tail": (proc.stderr or proc.stdout or "")[-800:],
                    "flags": TRACKS[track], "text": text, "runs": [],
                    "cold_ms": UNMEASURED, "warm_ms": []}
    finally:
        for pth in (out_path, log_path):
            try:
                os.unlink(pth)
            except OSError:
                pass


def _fmt(v) -> str:
    if v is None or v == UNMEASURED:
        return UNMEASURED
    if isinstance(v, (int, float)):
        return f"{v:,.1f}"
    return str(v)


def build_result(tracks: dict, verifier_engaged: dict, models: dict) -> dict:
    def track_block(t):
        d = tracks.get(t, {})
        if "error" in d:
            return {"label": TRACK_LABELS[t], "flags": TRACKS[t], "error": d["error"],
                    "cold_ms": UNMEASURED, "warm": summarize([]),
                    "runs": d.get("runs", []), "stderr_tail": d.get("stderr_tail", "")}
        warm = d.get("warm_ms", [])
        # representative metadata from the last successful warm run
        meta = {}
        for r in reversed(d.get("runs", [])):
            if r.get("status") == 200:
                meta = {k: r.get(k) for k in
                        ("relevance_llm_ms", "factual_verification_ms",
                         "relation_counts", "num_claims", "verifier_scores",
                         "verifier_errors", "prong_ms")}
                break
        return {
            "label": TRACK_LABELS[t],
            "flags": d.get("flags", TRACKS[t]),
            "text": d.get("text", TEXT),
            "cold_ms": d.get("cold_ms", UNMEASURED),
            "warm": summarize(warm),
            "metadata_last_warm_run": meta,
            "runs": d.get("runs", []),
        }

    return {
        "meta": {
            "path": "/evaluate",
            "method": "POST",
            "transport": "fastapi.testclient.TestClient(src.api.app), in-process; "
                         "each track in its own fresh subprocess so the cold call "
                         "includes that track's real model loads (no uvicorn, no TCP, no vLLM)",
            "request": {"prompt": PROMPT, "text": TEXT, "language": LANGUAGE},
            "n_warm_per_track": N_WARM,
            "n_warm_direct_model": N_MODEL_WARM,
            "percentile_definition": "linear interpolation (numpy 'linear')",
            "units": {
                "cold_ms": "wall clock of the first call in a fresh process (includes model loads)",
                "warm_ms": "wall clock of steady-state calls",
                "prong_ms": "prong_results[].processing_time from JSON (seconds, time.time()) x 1000",
            },
            "git": git_ref(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "not_measured": [
                "/generate-and-evaluate (needs a vLLM generation server with logprobs — "
                "no generator is running; out of scope)",
                "llm_verify /evaluate wall-clock on the plain Paris text does NOT include "
                "MiniCheck inference — that text's claims are all KB-confirmed, so the "
                "verifier never fires; use the 'verifier_engaged' row or the direct "
                "verifier timing for the MiniCheck cost",
            ],
        },
        "hardware": hardware_fingerprint(),
        "tracks": {t: track_block(t) for t in TRACK_ORDER},
        "verifier_engaged": track_block_verifier_engaged(verifier_engaged),
        "direct_model_timings": models,
    }


def track_block_verifier_engaged(d: dict) -> dict:
    if "error" in d:
        return {"label": "llm_verify engaged (KB-unknown claim text)",
                "error": d["error"], "cold_ms": UNMEASURED,
                "warm": summarize([]), "runs": d.get("runs", []),
                "stderr_tail": d.get("stderr_tail", "")}
    warm = d.get("warm_ms", [])
    meta = {}
    for r in reversed(d.get("runs", [])):
        if r.get("status") == 200:
            meta = {k: r.get(k) for k in
                    ("relevance_llm_ms", "factual_verification_ms",
                     "relation_counts", "num_claims", "verifier_scores",
                     "verifier_errors", "prong_ms")}
            break
    return {
        "label": "llm_verify engaged (KB-unknown claim text)",
        "flags": TRACKS["llm_verify"],
        "text": d.get("text", VERIFIER_ENGAGED_TEXT),
        "cold_ms": d.get("cold_ms", UNMEASURED),
        "warm": summarize(warm),
        "metadata_last_warm_run": meta,
        "runs": d.get("runs", []),
    }


def write_md(result: dict) -> list:
    hw = result["hardware"]
    tracks = result["tracks"]
    ve = result["verifier_engaged"]
    models = result["direct_model_timings"]
    L = []
    L.append("# Latency baseline — `/evaluate`, all shipped tracks (Phase 4)")
    L.append("")
    L.append(f"- Path: `POST /evaluate` via `fastapi.testclient.TestClient(src.api.app)` "
             f"(in-process; no uvicorn, no TCP, no vLLM)")
    L.append(f"- Request: prompt={PROMPT!r}, text={TEXT!r}, language=`{LANGUAGE}` "
             f"(per track: 1 cold + {N_WARM} warm; each track in a fresh process so the "
             f"cold call includes its real model loads)")
    L.append(f"- git: `{result['meta']['git']}`")
    L.append(f"- Timestamp (UTC): {result['meta']['timestamp_utc']}")
    L.append("")
    L.append(f"Hardware: `{hw['hostname']}` — {hw['cpu_model']}, "
             f"{hw['nproc']} CPUs, {hw['mem_total_gb']} GB RAM, "
             f"Python {hw['python_version']}, torch {hw['torch_version']}, "
             f"CUDA available={hw['cuda_available']} → {hw['compute']}")
    if hw.get("cuda_note"):
        L.append(f"- CUDA note: {hw['cuda_note']}")
    L.append("")
    L.append("## Per-track /evaluate wall-clock (ms)")
    L.append("")
    L.append("| Track | cold (first, incl. loads) | warm n | warm median | warm p95 | warm mean | warm min | warm max |")
    L.append("|---|---|---|---|---|---|---|---|")

    def trow(label, cold, w):
        return (f"| {label} | {_fmt(cold)} | {w['n']} | {_fmt(w['median'])} | "
                f"{_fmt(w['p95'])} | {_fmt(w['mean'])} | {_fmt(w['min'])} | {_fmt(w['max'])} |")

    for t in TRACK_ORDER:
        b = tracks[t]
        if "error" in b:
            L.append(f"| {TRACK_LABELS[t]} | ERROR: {b['error']} | — | — | — | — | — | — |")
        else:
            L.append(trow(TRACK_LABELS[t], b["cold_ms"], b["warm"]))
    if "error" in ve:
        L.append(f"| {ve['label']} | ERROR: {ve['error']} | — | — | — | — | — | — |")
    else:
        L.append(trow(ve["label"], ve["cold_ms"], ve["warm"]))
    L.append("")
    L.append("`cold` = the first call in a fresh process. Every track pays the shared "
             "model loads (MiniLM embeddings, toxic-bert, spaCy). The MiniCheck load "
             "(~6.4 s) is only paid by the `verifier_engaged` row — on the plain Paris "
             "text all claims are KB-confirmed, so the `llm_verify`/`all` rows never "
             "fire it. Judge/claims tracks add their first remote round trip on top.")
    L.append("")
    L.append("> Note: on the plain Paris text **every extracted claim is KB-confirmed**, so "
             "`llm_verify` (and `all`) do **not** invoke the MiniCheck verifier — their "
             "wall-clock ≈ baseline. The MiniCheck cost is measured in the `verifier_engaged` "
             "row (a KB-unknown claim) and in the direct verifier timing below.")
    L.append("")

    # metadata timings
    L.append("## Metadata timings the API already reports (last warm run, ms)")
    L.append("")
    L.append("| Track | Prong 1 ms | Prong 3 ms | Relevance llm_ms | Factual verification_ms | verifier_scores | relation_counts |")
    L.append("|---|---|---|---|---|---|---|")

    def mrow(label, meta):
        pm = (meta or {}).get("prong_ms") or {}
        p1 = pm.get("Prong 1", UNMEASURED)
        p3 = pm.get("Prong 3", UNMEASURED)
        rllm = (meta or {}).get("relevance_llm_ms")
        fv = (meta or {}).get("factual_verification_ms")
        vs = (meta or {}).get("verifier_scores") or []
        rc = (meta or {}).get("relation_counts") or {}
        rcs = ",".join(f"{k}:{v}" for k, v in rc.items()) if rc else "—"
        return (f"| {label} | {_fmt(p1)} | {_fmt(p3)} | {_fmt(rllm)} | {_fmt(fv)} | "
                f"{('[%s]' % ', '.join(f'{x:.3f}' for x in vs)) if vs else '—'} | {rcs} |")

    for t in TRACK_ORDER:
        b = tracks[t]
        if "error" not in b:
            L.append(mrow(TRACK_LABELS[t], b.get("metadata_last_warm_run")))
    if "error" not in ve:
        L.append(mrow(ve["label"], ve.get("metadata_last_warm_run")))
    L.append("")
    L.append("The verifier's per-claim latency is **not** exposed per-claim in the API "
             "response (only the FactualAccuracy `verification_time_ms` and the "
             "`verifier_score` per claim). Per the brief, the verifier is timed directly "
             "below.")
    L.append("")

    # direct model timings
    L.append("## Direct model-call timings (1 cold + " + str(N_MODEL_WARM) + " warm, ms)")
    L.append("")
    L.append("| Model | endpoint/model | cold (incl. load) | warm n | warm median | warm p95 | warm mean | warm min | warm max |")
    L.append("|---|---|---|---|---|---|---|---|---|")

    def drow(label, d, cold_key):
        cold = d.get(cold_key, UNMEASURED)
        w = summarize(d.get("warm_ms", []))
        return (f"| {label} | {d.get('model', '—')} | {_fmt(cold)} | {w['n']} | "
                f"{_fmt(w['median'])} | {_fmt(w['p95'])} | {_fmt(w['mean'])} | "
                f"{_fmt(w['min'])} | {_fmt(w['max'])} |")

    for key, label in (("judge", "judge (0.5B)"), ("claims", "claims (1.5B)"),
                       ("verifier", "verifier (MiniCheck 770M)")):
        d = models.get(key)
        if d is None:
            L.append(f"| {label} | — | ERROR | — | — | — | — | — | — |")
        else:
            cold_key = "cold_ms_includes_load" if key == "verifier" else "cold_ms"
            L.append(drow(label, d, cold_key))
    if "_llm_error" in models:
        L.append("")
        L.append(f"- LLM direct timings error: {models['_llm_error']}")
    if "_verifier_error" in models:
        L.append(f"- verifier direct timing error: {models['_verifier_error']}")
    L.append("")
    L.append("verifier `cold (incl. load)` = the first score call, which pays the one-time "
             "MiniCheck model load on CPU; warm = steady-state per-claim inference.")
    L.append("")

    # not measured
    L.append("## Not measured (this slice)")
    L.append("")
    for item in result["meta"]["not_measured"]:
        L.append(f"- {item}")
    L.append("")
    return L


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", choices=TRACKS, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--text", default=TEXT)
    args = ap.parse_args()

    if args.track:
        _worker(args.track, args.out, args.text)
        return

    print("measuring per-track /evaluate (fresh subprocess per track) ...", file=sys.stderr)
    tracks = {t: _spawn_track(t) for t in TRACK_ORDER}
    print("measuring llm_verify engaged (KB-unknown claim) ...", file=sys.stderr)
    verifier_engaged = _spawn_track("llm_verify", text=VERIFIER_ENGAGED_TEXT)
    print("measuring direct model timings ...", file=sys.stderr)
    models = direct_model_timings()

    result = build_result(tracks, verifier_engaged, models)
    out_dir = REPO_ROOT / "evaluation_results"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "latency_baseline.json"
    md_path = out_dir / "latency_baseline.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n")
    md_path.write_text("\n".join(write_md(result)))
    print(f"\nwrote {json_path}\nwrote {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
