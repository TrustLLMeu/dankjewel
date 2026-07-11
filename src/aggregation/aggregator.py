"""Score aggregation utilities."""

from typing import List, Dict
from src.base import ProngResult, DimensionScore


class ScoreAggregator:
    """Aggregate scores from multiple prongs.

    Only dimensions flagged `aggregate=True` contribute to a prong's
    average (and thus the total score) — purely descriptive/style axes
    (Hedging, Formality, Emotional Intensity, Modality Awareness, raw
    entropy measures, ...) have no universal "better" direction and are
    reported but excluded from the quality score. For dimensions whose
    natural scale isn't already [0,1]/higher-is-better (raw Perplexity,
    Uncertainty, Toxicity), `agg_value` supplies the orientation-corrected
    number used here instead of `value`.
    """

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

    @staticmethod
    def _contribution(dimension: DimensionScore) -> float:
        """Return the orientation-corrected, [0,1] value used for aggregation."""
        return dimension.agg_value if dimension.agg_value is not None else dimension.value

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

            # Store ALL dimension values for display (including
            # non-aggregated/descriptive ones) — unchanged from before.
            for dimension in result.dimensions:
                if dimension.name not in aggregated['dimension_scores']:
                    aggregated['dimension_scores'][dimension.name] = []
                aggregated['dimension_scores'][dimension.name].append(dimension.value)

            # Prong score = average of only the aggregate=True dimensions,
            # using their orientation-corrected contribution.
            scorable = [d for d in result.dimensions if d.aggregate]
            if scorable:
                prong_score = sum(self._contribution(d) for d in scorable) / len(scorable)
                aggregated['prong_scores'][result.prong_name] = prong_score

        # Calculate total score with weights
        total = 0.0
        total_weight = 0.0
        for prong_name, score in aggregated['prong_scores'].items():
            weight = self.weights.get(prong_name, 0.0)
            total += score * weight
            total_weight += weight

        # Renormalize if some prongs had no scorable dimensions / errored
        # out, so a missing prong doesn't silently drag the total down.
        aggregated['total_score'] = (total / total_weight) if total_weight > 0 else 0.5

        return aggregated

