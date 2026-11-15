"""Throughput and robustness matrix.

Runs the live cases the interface must survive and records the observed
state, then measures sequential throughput on the CPU host. Writes
evaluation_results/robustness.{json,md}.

Covered live here:
  - empty input
  - very long input (~20k chars)
  - non-English input (Dutch)
  - judge server down (dead port, in-process client)
  - claims server down (dead port, env-configured client)
Covered by the test suite instead of a live run (documented in the table):
  - verifier model load failure (tests/test_nli_verifier.py)
  - malformed model output (tests/test_llm_claim_extractor.py, test_tiny_judge.py)
  - timeout paths (same tests, MockTransport)

Run from the repo root:
    .venv/bin/python scripts/eval_robustness.py
"""

import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from src.api import app
from src.llm_judge_client import LLMJudgeClient
from src.extraction.llm_claim_extractor import LLMClaimExtractor

OUT_JSON = Path("evaluation_results/robustness.json")
OUT_MD = Path("evaluation_results/robustness.md")
DEAD = "http://127.0.0.1:18099/v1"


def dims_of(result):
    return {p["prong_name"]: p for p in result.get("prong_results", [])}


def evaluate(client, text, prompt="", **kw):
    t0 = time.perf_counter()
    resp = client.post("/evaluate", json={"text": text, "prompt": prompt, **kw})
    dt = (time.perf_counter() - t0) * 1000
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    return resp.status_code, body, dt


def case_empty(client):
    code, body, dt = evaluate(client, "")
    dims = [d for p in body.get("prong_results", []) for d in p.get("dimensions", [])]
    scored = sum(1 for d in dims if d.get("status") == "scored")
    return {"case": "empty input", "http": code,
            "observed": "evaluated without crash" if code < 400 else "rejected",
            "scored_dims": f"{scored}/{len(dims)}",
            "ms": round(dt, 1)}


def case_long(client):
    text = "Paris is the capital of France. " * 600  # ~20k chars
    code, body, dt = evaluate(client, text, "What is the capital of France?")
    claims = 0
    for prong in body.get("prong_results", []):
        if "Extraction" in prong["prong_name"]:
            fa = [d for d in prong["dimensions"] if d["name"] == "Factual Accuracy"]
            if fa:
                claims = fa[0]["metadata"].get("num_claims", 0)
    return {"case": "very long input (~21k chars)", "http": code,
            "observed": "evaluated", "claims": claims, "ms": round(dt, 1)}


def case_dutch(client):
    code, body, dt = evaluate(client, "Oslo is de hoofdstad van Noorwegen.",
                              "Wat is de hoofdstad van Noorwegen?", language="nl")
    prong1 = dims_of(body).get("LLM-as-Judge (Prong 1)")
    value = None
    if prong1:
        rel = [d for d in prong1["dimensions"] if d["name"] == "Relevance"]
        value = round(rel[0]["value"], 3) if rel else None
    return {"case": "non-English input (Dutch)", "http": code,
            "observed": "evaluated", "relevance": value, "ms": round(dt, 1)}


def case_judge_down():
    from src.prongs.prong1_dimensions import Relevance

    judge = LLMJudgeClient(base_url=DEAD, api_key="x", timeout=2)
    score = Relevance().evaluate("What is the capital of Norway?",
                                 "Oslo is the capital of Norway.", judge=judge)
    judge.close()
    return {"case": "judge server down", "http": "-",
            "observed": f"judge_status={score.metadata.get('judge_status')}",
            "baseline_kept": score.metadata.get("baseline_value") is not None}


def case_claims_down():
    os.environ["DANKJEWEL_CLAIMS_BASE_URL"] = DEAD
    try:
        client = LLMJudgeClient(timeout=2)
        extractor = LLMClaimExtractor(client=client)
        result = extractor.extract("Oslo is the capital of Norway.")
        client.close()
    finally:
        os.environ.pop("DANKJEWEL_CLAIMS_BASE_URL", None)
    meta = result.metadata or {}
    return {"case": "claims server down", "http": "-",
            "observed": f"claims={len(result.claims)} errors={len(meta.get('llm_errors', []))}",
            "spacy_track_kept": any(c.source in ("spacy", "both") for c in result.claims)}


def throughput(client, n, label, **kw):
    times = []
    for _ in range(n):
        _, _, dt = evaluate(client, "Oslo is the capital of Norway.", "What is the capital of Norway?", **kw)
        times.append(dt)
    times.sort()
    mean = statistics.mean(times)
    p95 = times[min(len(times) - 1, int(0.95 * len(times)))]
    return {"configuration": label, "n": n,
            "mean_ms": round(mean, 1), "p95_ms": round(p95, 1),
            "evals_per_min": round(60000.0 / mean, 1)}


def main():
    rows = []
    with TestClient(app) as client:
        rows.append(case_empty(client))
        rows.append(case_long(client))
        rows.append(case_dutch(client))
        rows.append(case_judge_down())
        rows.append(case_claims_down())

        tp = [throughput(client, 10, "default (all optional tracks off)"),
              throughput(client, 5, "all tracks on (judge + claims + verifier)",
                         tiny_judge=True, llm_extract=True, llm_verify=True)]

    host = {"cpu": platform.processor() or platform.machine(),
            "cpus": os.cpu_count(), "python": platform.python_version(),
            "cuda": False}

    report = {"host": host, "robustness": rows, "throughput": tp,
              "covered_by_tests": [
                  "verifier model load failure -> VerifierUnavailableError, status error (tests/test_nli_verifier.py)",
                  "malformed model JSON -> ClaimsParseError / judge parse path, status error (tests/test_llm_claim_extractor.py, tests/test_tiny_judge.py)",
                  "per-call timeouts -> unknown/error without blocking (same tests, MockTransport)",
              ]}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = ["# Robustness and throughput", "",
          f"Host: {host['cpu']}, {host['cpus']} CPUs, Python {host['python']}, CPU-only.",
          "", "## Robustness matrix", "",
          "| Case | HTTP | Observed | Extra |", "|---|---|---|---|"]
    for r in rows:
        extra = ", ".join(f"{k}={v}" for k, v in r.items()
                          if k not in ("case", "http", "observed"))
        md.append(f"| {r['case']} | {r['http']} | {r['observed']} | {extra} |")
    md += ["", "Not re-run live; covered by the tests:"] + [f"- {x}" for x in report["covered_by_tests"]]
    md += ["", "## Throughput (sequential, in-process)", "",
           "| Configuration | n | Mean | p95 | Evals/min |", "|---|---|---|---|---|"]
    for t in tp:
        md.append(f"| {t['configuration']} | {t['n']} | {t['mean_ms']} ms | {t['p95_ms']} ms | {t['evals_per_min']} |")
    md += ["", "Sequential measurements: the API runs one evaluation at a time per "
           "process. Concurrent throughput would need multiple workers and is not "
           "measured here."]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
