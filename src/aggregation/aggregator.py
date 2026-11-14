"""Score aggregation utilities."""

from typing import List, Dict
from src.base import ProngResult, DimensionScore


class ScoreAggregator:
    """Aggregate scores from multiple prongs.

    Only dimensions that are both `aggregate=True` and
    `status="scored"` contribute to a prong's average (and thus the
    total score). Dimensions with missing evidence (`status="unknown"`)
    or failed computations (`status="error"`) are reported in
    `dimension_scores` for display but never blended into a quality
    score — a missing measurement must not look like a middling 0.5.
    Prongs with no scored dimensions are omitted from `prong_scores`;
    if no prong contributed at all, `total_score` is None (JSON null)
    and `metadata['coverage']` is "none".
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
            'total_score': None,
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
            # non-aggregated/descriptive ones and unknown/error
            # placeholders) — the UI greys unknown/error dimensions.
            for dimension in result.dimensions:
                if dimension.name not in aggregated['dimension_scores']:
                    aggregated['dimension_scores'][dimension.name] = []
                aggregated['dimension_scores'][dimension.name].append(dimension.value)

            # Prong score = average of only the aggregate=True AND
            # status="scored" dimensions, using their orientation-
            # corrected contribution. Unknown/error dimensions never
            # enter the average.
            scorable = [d for d in result.dimensions
                        if d.aggregate and d.status == 'scored']
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
        # If NOTHING was scored, there is no total: report None (JSON
        # null), never a fake middling 0.5.
        if total_weight > 0:
            aggregated['total_score'] = total / total_weight

        # Coverage: how much of the weighted evaluation actually produced
        # scores — "full", "partial", or "none".
        weighted_prongs = {name for name, w in self.weights.items() if w > 0}
        scored_prongs = set(aggregated['prong_scores'])
        if not scored_prongs:
            coverage = 'none'
        elif weighted_prongs.issubset(scored_prongs):
            coverage = 'full'
        else:
            coverage = 'partial'
        aggregated['metadata']['coverage'] = coverage

        return aggregated

