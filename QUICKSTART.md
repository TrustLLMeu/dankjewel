# Quick Start Guide
## Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Download VADER sentiment lexicon
python3 -c "import nltk; nltk.download('vader_lexicon')"

# Download spaCy English model (required for Prong 3 claim extraction)
python3 -m spacy download en_core_web_sm

# Build offline Wikidata seed database (required for Prong 3 fact-checking)
python3 scripts/build_wikidata_db.py
```
## Basic Usage
### Run Example Evaluation
```bash
python3 main.py
```
This evaluates 4 example texts and outputs JSON results for each.

### Run with vLLM (Text Generation + Evaluation)

**Terminal 1 — Start the vLLM server:**
```bash
# Pick a model that fits your GPU (V100 32GB → 7B models work well)
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-1.5B-Instruct \
    --port 8000

# For larger models with 2 GPUs:
# python -m vllm.entrypoints.openai.api_server \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --port 8000 --tensor-parallel-size 2
```

**Terminal 2 — Start the IE API server:**
```bash
uvicorn src.api:app --host 0.0.0.0 --port 8080
```

**Terminal 3 — Open the control panel:**

Open **http://localhost:8080** in your browser. The HTML5 control panel lets you:
- Select a model, adjust temperature/top_p/penalties
- Generate text with real-time SSE streaming (tokens appear as they're generated)
- View all 4 prong evaluation scores with expandable dimension details
- Export results as JSON
- Browse evaluation history (stored in your browser's localStorage)

You can also test via curl:
```bash
# List available models
curl http://localhost:8080/models

# Generate + evaluate in one call
curl -X POST http://localhost:8080/generate-and-evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?", "model": "Qwen/Qwen2.5-1.5B-Instruct"}'

# Evaluate text without vLLM
curl -X POST http://localhost:8080/evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?", "text": "The capital of France is Paris."}'
```

### Run Benchmark (Compare Models)
```bash
python scripts/run_benchmark.py --vllm-url http://localhost:8000
# Results saved to evaluation_results/benchmark_results.json
```
### Evaluate Your Own Text
```python
from src.pipeline import EvaluationPipeline
# Create pipeline (enable specific prongs)
pipeline = EvaluationPipeline(enable_prongs=[2])  # Use rule-based only
# Evaluate text
text = "Hello, world! This is a test."
result = pipeline.evaluate(text)
# Get JSON output
json_result = pipeline.evaluate_to_json(text)
print(json_result)
```
### Output Format
Each evaluation returns a JSON structure with:
```json
{
  "text_length": 24,
  "prong_results": [...],
  "aggregated_scores": {
    "total_score": 0.5,
    "prong_scores": {...},
    "dimension_scores": {...}
  }
}
```
## Available Dimensions (Prong 2)
| Dimension | Score Range | Description |
|-----------|-------------|-------------|
| Fluency | 0.0 - 1.0 | Readability (higher = easier to read) |
| Politeness | 0.0 - 1.0 | Polite vs rude language (higher = more polite) |
| Emotional Intensity | 0.0 - 1.0 | Emotional expression strength |
| Formality | 0.0 - 1.0 | Formal vs casual (higher = more formal) |
| Hedging | 0.0 - 1.0 | Uncertainty/speculation (higher = more hedged) |
## Examples
### Example 1: Formal Text
```python
from src.pipeline import EvaluationPipeline
pipeline = EvaluationPipeline(enable_prongs=[2])
result = pipeline.evaluate("Dear Sir or Madam, I would like to inquire about your services.")
print(result['aggregated_scores']['dimension_scores'])
```
Expected output:
- High Fluency (1.0)
- High Formality (0.8+)
- High Politeness (0.6+)
### Example 2: Emotional Text
```python
pipeline = EvaluationPipeline(enable_prongs=[2])
result = pipeline.evaluate("OMG I'm SO excited!!! This is AMAZING!!!")
print(result['aggregated_scores']['dimension_scores'])
```
Expected output:
- High Emotional Intensity (0.8+)
- Low Formality (0.2)
### Example 3: Uncertain/Hedged Text
```python
pipeline = EvaluationPipeline(enable_prongs=[2])
result = pipeline.evaluate("It might be possible that perhaps things could change.")
print(result['aggregated_scores']['dimension_scores'])
```
Expected output:
- High Hedging (0.5+)
- High Formality (0.6)
## Advanced Usage
### Custom Aggregation Weights
```python
from src.aggregation.aggregator import ScoreAggregator
from src.prongs.prong2_rule_based import Prong2RuleBased
# Define custom weights
weights = {
    'Rule-Based (Prong 2)': 1.0  # Only use rule-based
}
# Create aggregator
aggregator = ScoreAggregator(weights=weights)
# Evaluate
prong2 = Prong2RuleBased()
result = prong2.evaluate("Test text")
# Aggregate
aggregated = aggregator.aggregate_prongs([result])
print(aggregated['total_score'])
```
### Single Dimension Evaluation
```python
from src.dimensions.prong2_dimensions import FluidityDimension
fluency = FluidityDimension()
score = fluency.evaluate("The cat sat on the mat.")
print(f"Fluency: {score.value:.2f}")
print(f"Raw Flesch Score: {score.raw_value:.1f}")
```
### Evaluate Multiple Texts
```python
from src.pipeline import EvaluationPipeline
pipeline = EvaluationPipeline(enable_prongs=[2])
texts = [
    "The quick brown fox jumps over the lazy dog.",
    "I'm so happy!!!",
    "Perhaps one might consider the possibility.",
]
for text in texts:
    result = pipeline.evaluate(text)
    score = result['aggregated_scores']['total_score']
    print(f"Text: {text[:40]}...")
    print(f"Score: {score:.2f}\n")
```
## Testing
```bash
# Run all tests
pytest tests/ -v
# Run specific test
pytest tests/test_prong2.py::test_prong2_basic_evaluation -v
# Run with coverage
pytest tests/ --cov=src
```
## Performance Notes
- **Prong 2 evaluation**: ~0.95 seconds per text
- **Parallel execution**: Prongs can be evaluated in parallel (not yet implemented)
- **Memory**: ~50MB baseline + ~10MB for Prong 2 dependencies
## Troubleshooting
### VADER not available
```bash
python3 -c "import nltk; nltk.download('vader_lexicon')"
```
### Module not found errors
```bash
pip install -r requirements.txt
```
### Text encoding issues
Ensure text is UTF-8 encoded. The system handles most Unicode characters.
## Next Steps
1. **Evaluate Your Data**: Use the pipeline on your texts
2. **Customize Weights**: Adjust aggregation weights for your use case
3. **Add More Dimensions**: Extend Prong 2 with custom dimensions
4. **Enable Other Prongs**: When Prongs 1, 3, 4 are implemented
## Documentation
- **README.md**: Full architecture and design documentation
- **IMPLEMENTATION_SUMMARY.txt**: Detailed implementation status
- **PROJECT_COMPLETION_REPORT.txt**: Complete project report
## Support
For issues or questions:
1. Check the documentation files
2. Review the code docstrings
3. Examine the test cases for usage examples
4. Check the example code in `main.py`
---
**Ready to start?** Run: `python3 main.py`
