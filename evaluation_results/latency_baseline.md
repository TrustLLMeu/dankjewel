# Latency baseline — `/evaluate` (slice 1, current system)

- Path: `POST /evaluate` via `fastapi.testclient.TestClient(src.api.app)` (in-process; no uvicorn, no TCP)
- Request: prompt='What is the capital of France?', text='The capital of France is Paris, in the north of the country.', language=`en`
- Runs: 2 warmup (discarded), 5 timed
- git: `feature/d75-v2 @ 0214efd`
- Timestamp (UTC): 2026-11-14T09:50:43+00:00

Hardware: `malvik` — Intel(R) Xeon(R) Gold 6132 CPU @ 2.60GHz, 56 CPUs, 754.52 GB RAM, Python 3.12.3, torch 2.15.0+cu132, CUDA available=False → CPU-only (CUDA init failed; torch built with CUDA, driver too old)
- Warmup wall clock (discarded, context only): [8900.4, 655.9] ms

## Latency (timed runs, ms)

| Metric | n | mean | std | min | max |
|---|---|---|---|---|---|
| HTTP /evaluate wall clock | 5 | 660.3 | 5.2 | 657.2 | 669.5 |
| LLM-as-Judge (Prong 1) processing_time | 5 | 643.7 | 3.7 | 640.1 | 649.9 |
| Rule-Based (Prong 2) processing_time | 5 | 0.5 | 0.1 | 0.4 | 0.6 |
| Extraction-Based (Prong 3) processing_time | 5 | 11.0 | 1.9 | 9.3 | 13.8 |
| Intrinsic (Prong 4) processing_time | 5 | 0.0 | 0.0 | 0.0 | 0.0 |
| Sum of prong processing times | 5 | 655.1 | 5.3 | 652.0 | 664.3 |
| aggregated_scores.metadata.total_time | 5 | 655.1 | 5.3 | 652.0 | 664.3 |

prong `processing_time` is reported by the pipeline in seconds (time.time() deltas); converted to ms (x1000) above.

Note: on `/evaluate` there is no vLLM `intrinsic_data`, so Prong 4 returns its Phase-1 neutral placeholders (its processing_time is trivially ~0 ms); Prong 4 real-logit latency is measured only via the generation paths.

## Not measured (this slice)

- /generate-and-evaluate (needs a vLLM generation server — out of slice 1)
- (none — all four prongs returned processing_time in every timed run)
