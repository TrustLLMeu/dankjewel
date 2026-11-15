# Interactive-path latency (`/generate-and-evaluate`)

**Measured:** 2026-11-15, by the Captain, on the measurement host (Intel Xeon Gold
6132, 56 CPUs, 755 GB RAM, CPU-only; Python 3.12; PyTorch 2.15).

## Setup

- API: the local Instant Evaluator on `http://127.0.0.1:8080` (all optional
  tracks off; same evaluation path as the `/evaluate` baseline).
- Generator: llama.cpp OpenAI-compatible server at `http://127.0.0.1:18093`
  (`Qwen/Qwen2.5-1.5B-Instruct`, Q4_K_M, CPU), used through the API's remote
  backend (`backend_type="remote"`, base URL without the `/v1` suffix).
- Request: prompt "Say hello in one sentence.", `max_tokens=32`,
  `temperature=0.0`, greedy decoding.
- Prong 4 received chat-completion logprobs; all four Intrinsic dimensions
  scored (`Uncertainty`, `Perplexity`, `Token Entropy`, `Semantic Entropy`).

## Results (1 cold + 5 warm)

| Call | Wall time |
|------|-----------|
| cold | 1,049 ms |
| warm 1 | 974 ms |
| warm 2 | 980 ms |
| warm 3 | 965 ms |
| warm 4 | 978 ms |
| warm 5 | 962 ms |

Warm median **974 ms**, p95 **980 ms**. The wall time covers generation
(32 tokens) plus the full evaluation and aggregation; the aggregate score for
this run was 0.776.

## Reproduction

```bash
curl -s http://127.0.0.1:8080/generate-and-evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hello in one sentence.",
       "model":"Qwen/Qwen2.5-1.5B-Instruct",
       "max_tokens":32,"temperature":0.0,
       "backend_type":"remote","base_url":"http://127.0.0.1:18093",
       "api_key":"<local llama.cpp key>"}'
```

`scripts/measure_latency.py` covers `/evaluate` only; this file is the record for
the interactive path. Long or hosted generations are not covered by this
measurement.
