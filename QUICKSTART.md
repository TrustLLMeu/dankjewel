# Quick Start Guide

## Installation

### Standard install (CPU only — no GPU required)

```bash
pip install -r requirements-minimal.txt
python3 -c "import nltk; nltk.download('vader_lexicon')"
python3 -m spacy download en_core_web_sm
python3 scripts/build_wikidata_db.py
```

This covers all four prongs. No local vLLM server or GPU is needed:

- **Prongs 1–3** run entirely on CPU.
- **Prong 4** works when you supply a remote OpenAI-compatible API key
  (OpenAI, Groq, Fireworks, OpenRouter, etc.) in the UI's Backend Selector.
  If the provider does not return per-token logprobs, Prong 4 shows neutral
  placeholder scores — the other prongs are unaffected.

A local vLLM server (`requirements.txt`, CUDA GPU) is only needed if you want
to run model generation **on your own machine**.

**Python 3.12+ required.**

---

## Run the CLI Example

```bash
python3 main.py
```

Evaluates 4 sample texts across all prongs and saves results to
`evaluation_results/evaluation_results.json`.

---

## Run the Web UI (generate + evaluate)

**Terminal 1 — Start a vLLM server** (skip if you'll use a remote API key):

```bash
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-1.5B-Instruct \
    --port 8000

# 2-GPU larger model:
# python -m vllm.entrypoints.openai.api_server \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --port 8000 --tensor-parallel-size 2
```

Any OpenAI-compatible server works, including llama.cpp on CPU. Point the app
at it and pass its key when it requires one:

```bash
VLLM_BASE_URL=http://127.0.0.1:18091 VLLM_API_KEY=<server key> \
    uvicorn src.api:app --host 127.0.0.1 --port 8080
```

The client accepts both the vLLM `data` shape and the llama.cpp `models` shape
for `/v1/models`, and both the legacy and chat-shaped `logprobs`, so Prong 4
still scores from a llama.cpp generator.

**Terminal 2 — Start the IE API server:**

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8080
```

**Open http://localhost:8080** in your browser. Features:

- **Backend selector:** Local vLLM (`http://localhost:8000`) or any remote
  OpenAI-compatible host (bring-your-own-key — key is never stored server-side)
- **Generation parameters:** temperature, top-p, repetition/frequency penalties,
  max tokens
- **Real-time streaming:** tokens appear as they're generated via SSE
- **Score visualization:** gauge for total score, expandable prong cards with
  per-dimension bars and computation-method tags (`exact` / `approx.`)
- **History:** stored in browser localStorage, exportable as JSON

**Note:** Most hosted OpenAI-compatible providers return limited logprobs on chat
completions, so Prong 4 may show neutral placeholder scores for remote backends.
Local vLLM with `--logprobs 20` gives full intrinsic metrics.

---

## Evaluate Text (No Generation, No GPU Required)

```bash
# Health check
curl http://localhost:8080/health

# List models (requires vLLM or remote backend configured)
curl http://localhost:8080/models

# Evaluate pre-written text (no LLM needed)
curl -X POST http://localhost:8080/evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?",
       "text": "The capital of France is Paris.",
       "lang": "en"}'

# Generate and evaluate in one call (requires vLLM)
curl -X POST http://localhost:8080/generate-and-evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?",
       "model": "Qwen/Qwen2.5-1.5B-Instruct"}'
```

---

## Python API

### Full pipeline

```python
from src.pipeline import EvaluationPipeline

pipeline = EvaluationPipeline(enable_prongs=[1, 2, 3, 4])
result = pipeline.evaluate(
    text="The capital of France is Paris.",
    prompt="What is the capital of France?",
    lang="en",
)
print(result["aggregated_scores"]["total_score"])
print(pipeline.evaluate_to_json(
    text="The capital of France is Paris.",
    prompt="What is the capital of France?",
))
```

### Rule-based only (Prong 2, CPU, fast)

```python
from src.pipeline import EvaluationPipeline
pipeline = EvaluationPipeline(enable_prongs=[2])
result = pipeline.evaluate("Dear Sir, I would like to inquire about your services.", lang="en")
print(result["aggregated_scores"]["dimension_scores"])
```

### Single dimension

```python
from src.dimensions.prong2_dimensions import FluidityDimension
fluency = FluidityDimension()
score = fluency.evaluate("The cat sat on the mat.", lang="en")
print(f"Fluency: {score.value:.3f}  (raw Flesch: {score.raw_value})")
```

---

## Supported Languages (Prong 2)

| Code | Language |
|------|----------|
| `en` | English |
| `da` | Danish |
| `de` | German |
| `nl` | Dutch |
| `fo` | Faroese |
| `is` | Icelandic |
| `nb` | Norwegian Bokmål |
| `nn` | Norwegian Nynorsk |
| `sv` | Swedish |

Pass `lang=` to `pipeline.evaluate()` or to prong-level `evaluate()` calls.
The optional `tiny_judge` track is routed by `lang`: English → the 0.5B judge
(`DANKJEWEL_JUDGE_BASE_URL`), other languages → the 1.5B
(`DANKJEWEL_JUDGE_BASE_URL_NONEN`, `DANKJEWEL_JUDGE_MODEL_NONEN`).

---

## Run the FEVER 2.0 Benchmark (Prong 3)

```bash
# Full dataset against the seed DB (operational baseline)
python scripts/eval_fever2.py

# Balanced 300-claim subsample against the oracle DB
python scripts/eval_fever2.py \
    --db-path data/wikidata_fever.db \
    --sample-path data/fever2_oracle_sample.jsonl \
    --output-suffix oracle

# Results written to evaluation_results/
```

---

## Testing

```bash
pytest tests/ -v              # all tests
pytest tests/test_prong2.py -v
pytest tests/test_prong4.py -v
pytest tests/ --cov=src       # with coverage
```

---

## Troubleshooting

**VADER not found:**
```bash
python3 -c "import nltk; nltk.download('vader_lexicon')"
```

**spaCy model missing:**
```bash
python3 -m spacy download en_core_web_sm
```

**Wikidata DB not found:**
```bash
python3 scripts/build_wikidata_db.py
```

**Module not found / import errors:**
```bash
pip install -r requirements.txt
```

**Prong 4 shows neutral 0.5 scores:** vLLM is either not running or the
remote provider does not return per-token logprobs. Use a local vLLM server or
see `ASSUMPTIONS.md` A13/A14.

---

## Documentation

| File | Contents |
|------|----------|
| `README.md` | Architecture, all dimensions, aggregation, benchmarks |
| `ASSUMPTIONS.md` | Scientific assumptions and design trade-offs |
| `TODO.md` | Planned LLM-based dimension upgrades |
| `DB_EXTENSION_GUIDE.md` | Increasing Wikidata coverage |
| `CONTRIBUTING.md` | Branch/PR workflow |
| `LICENSE` | Apache 2.0 |
