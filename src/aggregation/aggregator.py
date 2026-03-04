"""Score aggregation utilities."""

from typing import List, Dict
from src.base import ProngResult, DimensionScore


class ScoreAggregator:
    """Aggregate scores from multiple prongs."""

    def __init__(self, weights: Dict[str, float] = None):
        """
        Initialize aggregator with optional weights.

        Default: equal weight for all prongs (0.25 each).
        """
        self.weights = weights or {
            'LLM-as-Judge (Prong 1)': 0.25,
            'Rule-Based (Prong 2)': 0.25,
            'Extraction-Based (Prong 3)': 0.25,
            'Intrinsic (Prong 4)': 0.25
        }

    def aggregate_prongs(self, results: List[ProngResult]) -> Dict:
        """Aggregate results from multiple prongs."""
        aggregated = {
            'total_score': 0.0,
            'prong_scores': {},
            'dimension_scores': {},
            'metadata': {
                'num_prongs': len(results),
                'total_time': sum(r.processing_time for r in results)
            }
        }

        for result in results:
            if result.error:
                continue

            # Calculate prong score as average of its dimensions
            if result.dimensions:
                prong_score = sum(d.value for d in result.dimensions) / len(result.dimensions)
                aggregated['prong_scores'][result.prong_name] = prong_score

                # Store dimension scores
                for dimension in result.dimensions:
                    if dimension.name not in aggregated['dimension_scores']:
                        aggregated['dimension_scores'][dimension.name] = []
                    aggregated['dimension_scores'][dimension.name].append(dimension.value)

        # Calculate total score with weights
        total = 0.0
        for prong_name, score in aggregated['prong_scores'].items():
            weight = self.weights.get(prong_name, 0.0)
            total += score * weight

        aggregated['total_score'] = total

        return aggregated

