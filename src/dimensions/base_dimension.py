"""Base classes for dimensions."""

from src.base import Dimension, DimensionScore


class ScorableDimension(Dimension):
    """Base class for dimensions that score text."""

    def normalize_score(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize a score to 0.0-1.0 range."""
        if max_val == min_val:
            return 0.5
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

    def create_score(self, value: float, raw_value=None, metadata=None) -> DimensionScore:
        """Create a DimensionScore with this dimension's name."""
        if metadata is None:
            metadata = {}
        return DimensionScore(
            name=self.name,
            value=value,
            raw_value=raw_value,
            metadata=metadata
        )

