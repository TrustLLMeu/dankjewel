# Latency baseline — `/evaluate` (slice 1, current system)

- Path: `POST /evaluate` via `fastapi.testclient.TestClient(src.api.app)` (in-process; no uvicorn, no TCP)
- Request: prompt='What is the capital of France?', text='The capital of France is Paris, in the north of the country.', language=`en`
- Runs: 2 warmup (discarded), 5 timed
- git: `feature/d75-v2 @ feature/d75-v2`
- Timestamp (UTC): 2026-11-14T09:45:34+00:00

Hardware: `malvik` — Intel(R) Xeon(R) Gold 6132 CPU @ 2.60GHz, 56 CPUs, 754.52 GB RAM, Python 3.12.3, torch 2.15.0+cu132, CUDA available=False → CPU-only (CUDA init failed; torch built with CUDA, driver too old)
- Warmup wall clock (discarded, context only): [8738.4, 662.6] ms

## Latency (timed runs, ms)

| Metric | n | mean | std | min | max |
|---|---|---|---|---|---|
| HTTP /evaluate wall clock | 5 | 661.7 | 5.8 | 656.7 | 670.0 |
| LLM-as-Judge (Prong 1) processing_time | 5 | 647.4 | 4.3 | 643.4 | 652.6 |
| Rule-Based (Prong 2) processing_time | 5 | 0.5 | 0.0 | 0.5 | 0.5 |
| Extraction-Based (Prong 3) processing_time | 5 | 9.9 | 1.5 | 9.2 | 12.7 |
| Intrinsic (Prong 4) processing_time | 5 | 0.0 | 0.0 | 0.0 | 0.0 |
| Sum of prong processing times | 5 | 657.9 | 5.5 | 653.1 | 665.9 |
| aggregated_scores.metadata.total_time | 5 | 657.9 | 5.5 | 653.1 | 665.9 |

prong `processing_time` is reported by the pipeline in seconds (time.time() deltas); converted to ms (x1000) above.

## Not measured (this slice)

- /generate-and-evaluate (needs a vLLM generation server — out of slice 1)
- (none — all four prongs returned processing_time in every timed run)
