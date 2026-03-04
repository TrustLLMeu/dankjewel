#!/usr/bin/env python3
"""Run benchmark claims through vLLM models and evaluate with IE.

Reads data/benchmark_claims.json, generates responses from each available
vLLM model, evaluates with the IE pipeline, and saves results to
evaluation_results/benchmark_results.json.

Usage:
    python scripts/run_benchmark.py [--vllm-url http://localhost:8000]
                                     [--models model1,model2]
                                     [--output evaluation_results/benchmark_results.json]

Requires a running vLLM server.
"""

import asyncio
import argparse
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.vllm_client import VLLMClient
from src.pipeline import EvaluationPipeline


async def run_benchmark(
    vllm_url: str,
    model_filter: list = None,
    claims_path: str = "data/benchmark_claims.json",
    output_path: str = "evaluation_results/benchmark_results.json",
    max_tokens: int = 256,
    temperature: float = 0.3,
):
    """Run the benchmark suite."""
    # Load claims
    with open(claims_path) as f:
        claims = json.load(f)
    print(f"Loaded {len(claims)} benchmark claims from {claims_path}")

    # Connect to vLLM
    client = VLLMClient(base_url=vllm_url)

    # Check health
    healthy = await client.health_check()
    if not healthy:
        print(f"ERROR: vLLM server at {vllm_url} is not reachable.")
        print("Start it with:")
        print(f"  python -m vllm.entrypoints.openai.api_server --model <model> --port 8000")
        await client.close()
        return

    # Get available models
    all_models = await client.list_models()
    print(f"Available models: {all_models}")

    if model_filter:
        models = [m for m in all_models if m in model_filter]
        if not models:
            print(f"ERROR: None of {model_filter} found in available models")
            await client.close()
            return
    else:
        models = all_models

    print(f"Will benchmark: {models}")

    # Initialize evaluator
    evaluator = EvaluationPipeline(enable_prongs=[1, 2, 3, 4])

    results = []
    total = len(models) * len(claims)
    done = 0

    for model in models:
        print(f"\n{'='*60}")
        print(f"Model: {model}")
        print(f"{'='*60}")

        for claim in claims:
            done += 1
            prompt = claim["prompt_template"]

            try:
                # Generate
                gen = await client.generate(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                # Evaluate
                eval_result = evaluator.evaluate(
                    text=gen.text,
                    prompt=prompt,
                )

                # Extract key scores
                prong_scores = eval_result.get('aggregated_scores', {}).get('prong_scores', {})
                dim_scores = eval_result.get('aggregated_scores', {}).get('dimension_scores', {})

                result_entry = {
                    "model": model,
                    "claim_id": claim["id"],
                    "claim": claim["claim"],
                    "ground_truth": claim["ground_truth"],
                    "category": claim["category"],
                    "prompt": prompt,
                    "generated_text": gen.text,
                    "generation_time_ms": gen.generation_time_ms,
                    "num_tokens": len(gen.tokens) if gen.tokens else 0,
                    "total_score": eval_result.get('aggregated_scores', {}).get('total_score'),
                    "prong_scores": prong_scores,
                    "factual_accuracy": (dim_scores.get('Factual Accuracy', [0.5]))[0],
                    "factual_consistency": (dim_scores.get('Factual Consistency', [1.0]))[0],
                    "temporal_accuracy": (dim_scores.get('Temporal Accuracy', [0.5]))[0],
                    "toxicity": (dim_scores.get('Toxicity', [0.0]))[0],
                    "fluency": (dim_scores.get('Fluency', [0.5]))[0],
                }
                results.append(result_entry)

                status = "✅" if gen.finish_reason == "stop" else "⚠️"
                print(f"  [{done}/{total}] {status} {claim['id']}: "
                      f"accuracy={result_entry['factual_accuracy']:.2f} "
                      f"fluency={result_entry['fluency']:.2f} "
                      f"({gen.generation_time_ms:.0f}ms)")

            except Exception as e:
                print(f"  [{done}/{total}] ❌ {claim['id']}: {e}")
                results.append({
                    "model": model,
                    "claim_id": claim["id"],
                    "error": str(e),
                })

    # Save results
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n{'='*60}")
    print(f"✅ Benchmark results saved to {output_path}")
    print(f"   {len(results)} evaluations across {len(models)} model(s)")
    print(f"{'='*60}")

    await client.close()


def main():
    parser = argparse.ArgumentParser(description='Run IE benchmark against vLLM models')
    parser.add_argument('--vllm-url', default='http://localhost:8000',
                        help='vLLM server URL')
    parser.add_argument('--models', default=None,
                        help='Comma-separated list of model IDs to benchmark (default: all)')
    parser.add_argument('--claims', default='data/benchmark_claims.json',
                        help='Path to benchmark claims JSON')
    parser.add_argument('--output', default='evaluation_results/benchmark_results.json',
                        help='Output path for results')
    parser.add_argument('--max-tokens', type=int, default=256)
    parser.add_argument('--temperature', type=float, default=0.3)
    args = parser.parse_args()

    model_filter = args.models.split(',') if args.models else None

    asyncio.run(run_benchmark(
        vllm_url=args.vllm_url,
        model_filter=model_filter,
        claims_path=args.claims,
        output_path=args.output,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    ))


if __name__ == '__main__':
    main()


