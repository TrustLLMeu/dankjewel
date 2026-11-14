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

    def create_score(self, value: float, raw_value=None, metadata=None,
                      aggregate: bool = True, agg_value: float = None,
                      status: str = "scored") -> DimensionScore:
        """Create a DimensionScore with this dimension's name.

        Args:
            value: the dimension's own natural-scale score (unchanged meaning).
            raw_value: pre-normalization value, for transparency.
            metadata: additional diagnostic info.
            aggregate: whether this dimension counts toward the parent
                prong's average (False for purely descriptive/style axes
                with no universal "better" direction).
            agg_value: explicit [0,1] higher-is-better value to use for
                aggregation instead of `value`, when `value`'s natural
                scale isn't already [0,1]/higher-is-better (e.g. raw
                Perplexity, or Uncertainty/Toxicity which are higher=worse).
            status: "scored" for a genuine measurement (default),
                "unknown" when the evidence needed to measure was
                missing (value becomes a display-only placeholder),
                "error" when the computation raised an exception.
                Anything but "scored" is excluded from aggregation.
        """
        if metadata is None:
            metadata = {}
        return DimensionScore(
            name=self.name,
            value=value,
            raw_value=raw_value,
            metadata=metadata,
            aggregate=aggregate,
            agg_value=agg_value,
            status=status,
        )

