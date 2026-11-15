# Latency baseline — `/evaluate`, all shipped tracks (Phase 4)

- Path: `POST /evaluate` via `fastapi.testclient.TestClient(src.api.app)` (in-process; no uvicorn, no TCP, no vLLM)
- Request: prompt='What is the capital of France?', text='The capital of France is Paris, in the north of the country.', language=`en` (per track: 1 cold + 5 warm; each track in a fresh process so the cold call includes its real model loads)
- git: `feature/d75-v2 @ 4bd4637`
- Timestamp (UTC): 2026-11-14T20:19:46+00:00

Hardware: `malvik` — Intel(R) Xeon(R) Gold 6132 CPU @ 2.60GHz, 56 CPUs, 754.52 GB RAM, Python 3.12.3, torch 2.15.0+cu132, CUDA available=False → CPU-only (CUDA init failed; torch built with CUDA, driver too old)

## Per-track /evaluate wall-clock (ms)

| Track | cold (first, incl. loads) | warm n | warm median | warm p95 | warm mean | warm min | warm max |
|---|---|---|---|---|---|---|---|
| baseline (all flags off) | 9,215.3 | 5 | 671.7 | 684.1 | 670.4 | 660.0 | 686.8 |
| tiny_judge only (0.5B judge) | 9,482.4 | 5 | 770.3 | 782.6 | 771.5 | 758.8 | 783.1 |
| llm_extract only (1.5B claims) | 9,693.5 | 5 | 907.6 | 946.2 | 912.8 | 889.4 | 955.5 |
| llm_verify only (MiniCheck NLI) | 9,332.5 | 5 | 654.0 | 677.6 | 661.8 | 651.5 | 679.3 |
| all three on | 9,196.3 | 5 | 1,008.2 | 1,048.5 | 1,013.1 | 991.0 | 1,057.8 |
| llm_verify engaged (KB-unknown claim text) | 11,072.0 | 5 | 826.5 | 946.4 | 858.5 | 824.8 | 972.2 |

`cold` = the first call in a fresh process (includes every model load that track triggers — e.g. MiniLM+toxic-bert+spaCy for every track, MiniCheck ~tens of s for the verifier track, plus the remote judge/claims round trips). `warm` = the 5 steady-state calls after it.

> Note: on the plain Paris text **every extracted claim is KB-confirmed**, so `llm_verify` (and `all`) do **not** invoke the MiniCheck verifier — their wall-clock ≈ baseline. The MiniCheck cost is measured in the `verifier_engaged` row (a KB-unknown claim) and in the direct verifier timing below.

## Metadata timings the API already reports (last warm run, ms)

| Track | Prong 1 ms | Prong 3 ms | Relevance llm_ms | Factual verification_ms | verifier_scores | relation_counts |
|---|---|---|---|---|---|---|
| baseline (all flags off) | 657.0 | 11.5 | unmeasured | 0.3 | — | confirmed:2,denied:0,partially_supported:0,conflated:0,unknown:0 |
| tiny_judge only (0.5B judge) | 759.7 | 11.2 | 104.3 | 0.4 | — | confirmed:2,denied:0,partially_supported:0,conflated:0,unknown:0 |
| llm_extract only (1.5B claims) | 660.7 | 239.4 | unmeasured | 0.4 | — | confirmed:1,denied:0,partially_supported:0,conflated:0,unknown:0 |
| llm_verify only (MiniCheck NLI) | 658.2 | 15.0 | unmeasured | 0.4 | — | confirmed:2,denied:0,partially_supported:0,conflated:0,unknown:0 |
| all three on | 757.3 | 244.5 | 100.8 | 0.3 | — | confirmed:1,denied:0,partially_supported:0,conflated:0,unknown:0 |
| llm_verify engaged (KB-unknown claim text) | 625.0 | 197.8 | unmeasured | 189.6 | [0.012] | confirmed:0,denied:1,partially_supported:0,conflated:0,unknown:0 |

The verifier's per-claim latency is **not** exposed per-claim in the API response (only the FactualAccuracy `verification_time_ms` and the `verifier_score` per claim). Per the brief, the verifier is timed directly below.

## Direct model-call timings (1 cold + 20 warm, ms)

| Model | endpoint/model | cold (incl. load) | warm n | warm median | warm p95 | warm mean | warm min | warm max |
|---|---|---|---|---|---|---|---|---|
| judge (0.5B) | Qwen/Qwen2.5-0.5B-Instruct | 267.9 | 20 | 76.3 | 84.7 | 77.8 | 73.1 | 93.1 |
| claims (1.5B) | Qwen/Qwen2.5-1.5B-Instruct | 220.0 | 20 | 210.9 | 212.9 | 210.8 | 208.8 | 213.0 |
| verifier (MiniCheck 770M) | lytang/MiniCheck-Flan-T5-Large | 6,395.8 | 20 | 196.4 | 206.3 | 196.2 | 185.7 | 209.7 |

verifier `cold (incl. load)` = the first score call, which pays the one-time MiniCheck model load on CPU; warm = steady-state per-claim inference.

## Not measured (this slice)

- /generate-and-evaluate (needs a vLLM generation server with logprobs — no generator is running; out of scope)
- llm_verify /evaluate wall-clock on the plain Paris text does NOT include MiniCheck inference — that text's claims are all KB-confirmed, so the verifier never fires; use the 'verifier_engaged' row or the direct verifier timing for the MiniCheck cost
