"""Main evaluation pipeline."""

import json
from typing import List
from src.prongs import Prong1LLMAsJudge, Prong2RuleBased, Prong3Extraction, Prong4Intrinsic
from src.aggregation.aggregator import ScoreAggregator


class EvaluationPipeline:
    """Main pipeline for multi-dimensional text evaluation."""

    def __init__(self, enable_prongs: List[int] = None):
        """
        Initialize the evaluation pipeline.

        Args:
            enable_prongs: List of prong numbers to enable (1-4). Defaults to all.
        """
        if enable_prongs is None:
            enable_prongs = [1, 2, 3, 4]

        self.prongs = {}
        self.aggregator = ScoreAggregator()

        if 1 in enable_prongs:
            self.prongs['Prong 1'] = Prong1LLMAsJudge()
        if 2 in enable_prongs:
            self.prongs['Prong 2'] = Prong2RuleBased()
        if 3 in enable_prongs:
            self.prongs['Prong 3'] = Prong3Extraction()
        if 4 in enable_prongs:
            self.prongs['Prong 4'] = Prong4Intrinsic()

    def evaluate(self, text: str, prompt: str = None, intrinsic_data=None) -> dict:
        """
        Evaluate text across all enabled prongs.

        Args:
            text: The text to evaluate
            prompt: Optional prompt/query that generated the text (used by Prong 1 for relevance)
            intrinsic_data: Optional IntrinsicData from vLLM for Prong 4.
                           If None, Prong 4 returns neutral placeholder scores.

        Returns:
            Dictionary containing all prong results and aggregated scores
        """
        results = []

        for prong_name, prong in self.prongs.items():
            try:
                if prong_name == 'Prong 4':
                    result = prong.evaluate(text, intrinsic_data=intrinsic_data)
                elif prong_name == 'Prong 1':
                    # Prong 1 uses prompt for relevance scoring
                    result = prong.evaluate(text, prompt=prompt)
                else:
                    result = prong.evaluate(text)
                results.append(result)
            except Exception as e:
                print(f"Error in {prong_name}: {e}")

        # Aggregate results
        aggregated = self.aggregator.aggregate_prongs(results)

        # Build final output
        output = {
            'text_length': len(text),
            'prong_results': [r.to_dict() for r in results],
            'aggregated_scores': aggregated
        }

        return output

    def evaluate_to_json(self, text: str, prompt: str = None, intrinsic_data=None) -> str:
        """
        Evaluate text and return results as JSON string.

        Args:
            text: The text to evaluate
            prompt: Optional prompt/query that generated the text
            intrinsic_data: Optional IntrinsicData from vLLM for Prong 4

        Returns:
            JSON string of evaluation results
        """
        results = self.evaluate(text, prompt=prompt, intrinsic_data=intrinsic_data)
        return json.dumps(results, indent=2)

