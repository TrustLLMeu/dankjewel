"""
Main entry point for the online evaluation system.

This demonstrates the multi-dimensional text evaluation pipeline
based on the TrustLLM Deliverable 7.5 protocol.
"""

import json
from pathlib import Path
from src.pipeline import EvaluationPipeline


def main():
    """Run example evaluation and save results to file."""
    # Initialize pipeline with all prongs enabled
    pipeline = EvaluationPipeline(enable_prongs=[1, 2, 3, 4])

    # Example texts to evaluate (with optional prompts for Prong 1)
    example_texts = [
        ("Explain biathlon.", "Biathlon combines cross-country skiing and rifle shooting in a winter sport."),
        ("Tell me about the weather.", "Today is sunny and warm with temperatures around 25 degrees."),
        ("Explan why I am an idiot!", "You are such a moron! This is devastating!!!"),
        ("What is the capital of France?", "The capital of France is Paris, located in north-central France."),
        ("Let me know if you are really sure.", "I kind of don't know because there are maybe more things to take into consideration.")
    ]

    # Create output directory
    output_dir = Path("evaluation_results")
    output_dir.mkdir(exist_ok=True)

    # Collect all results
    all_results = []

    # Evaluate each text
    for i, (prompt, text) in enumerate(example_texts, 1):
        print(f"\n{'='*80}")
        print(f"EVALUATION {i}: {text[:50]}...")
        print(f"{'='*80}")
        if prompt:
            print(f"Prompt: {prompt}")

        try:
            result = pipeline.evaluate(text, prompt=prompt)
            all_results.append({
                "evaluation_id": i,
                "prompt": prompt,
                "text": text,
                "result": result
            })
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error during evaluation: {e}")
            import traceback
            traceback.print_exc()

    # Save all results to JSON file
    output_file = output_dir / "evaluation_results.json"
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n{'='*80}")
    print(f"✅ Results saved to {output_file}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
