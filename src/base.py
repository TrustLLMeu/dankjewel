"""Base classes for the evaluation system."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
import json


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension.

    `value` is the dimension's own natural scale/orientation (e.g.
    "Uncertainty" is legitimately higher=worse, "Perplexity" is a raw,
    unbounded, lower=better number) — it must NOT be silently reinterpreted,
    since callers/tests read it directly for its documented meaning.

    Aggregation (averaging into a prong score / total score) requires a
    common [0,1], higher=better scale. Two fields support this without
    touching `value`:
      - `aggregate`: whether this dimension should count toward the
        parent prong's average at all. Purely descriptive/style axes
        (e.g. Hedging, Formality, Emotional Intensity, Modality
        Awareness, token/semantic entropy) have no universally "better"
        direction and are excluded (aggregate=False) — they are still
        reported, just not blended into a quality score.
      - `agg_value`: an explicit [0,1], higher=better value to use for
        aggregation INSTEAD of `value`, for dimensions whose natural
        scale isn't already [0,1]-higher-is-better (e.g. Perplexity,
        Uncertainty, Toxicity). If None, the aggregator falls back to
        using `value` as-is (only valid when `value` is already
        [0,1]/higher=better).
    """
    name: str
    value: float  # dimension's own natural scale — see class docstring
    raw_value: Any = None  # Original value before normalization
    metadata: Dict[str, Any] = None
    aggregate: bool = True
    agg_value: float = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'value': self.value,
            'raw_value': self.raw_value,
            'metadata': self.metadata,
            'aggregate': self.aggregate,
            'agg_value': self.agg_value,
        }


@dataclass
class ProngResult:
    """Result from a single prong evaluation."""
    prong_name: str
    dimensions: List[DimensionScore]
    processing_time: float
    error: str = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'prong_name': self.prong_name,
            'dimensions': [d.to_dict() for d in self.dimensions],
            'processing_time': self.processing_time,
            'error': self.error
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class Dimension(ABC):
    """Base class for evaluation dimensions."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evaluate(self, text: str, **kwargs) -> DimensionScore:
        """Evaluate text and return a DimensionScore."""
        pass


class Evaluator(ABC):
    """Base class for prong evaluators."""

    def __init__(self, prong_name: str):
        self.prong_name = prong_name
        self.dimensions: Dict[str, Dimension] = {}

    def register_dimension(self, dimension: Dimension) -> None:
        """Register a dimension for evaluation."""
        self.dimensions[dimension.name] = dimension

    @abstractmethod
    def evaluate(self, text: str, **kwargs) -> ProngResult:
        """Evaluate text using this prong."""
        pass

