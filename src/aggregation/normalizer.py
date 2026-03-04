"""Score normalization utilities."""

from typing import List
from src.base import DimensionScore


class ScoreNormalizer:
    """Normalize dimension scores to 0.0-1.0 range."""

    @staticmethod
    def normalize_scores(scores: List[DimensionScore]) -> List[DimensionScore]:
        """Normalize a list of scores using min-max normalization."""
        if not scores:
            return scores

        # Group by dimension name
        by_dimension = {}
        for score in scores:
            if score.name not in by_dimension:
                by_dimension[score.name] = []
            by_dimension[score.name].append(score)

        normalized = []
        for dimension_name, dimension_scores in by_dimension.items():
            values = [s.value for s in dimension_scores if s.value is not None]

            if not values:
                continue

            min_val = min(values)
            max_val = max(values)

            for score in dimension_scores:
                if score.value is None:
                    norm_value = 0.5
                else:
                    if max_val == min_val:
                        norm_value = 0.5
                    else:
                        norm_value = (score.value - min_val) / (max_val - min_val)

                norm_score = DimensionScore(
                    name=score.name,
                    value=max(0.0, min(1.0, norm_value)),
                    raw_value=score.raw_value,
                    metadata=score.metadata
                )
                normalized.append(norm_score)

        return normalized

