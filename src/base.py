"""Base classes for the evaluation system."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
import json


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""
    name: str
    value: float  # 0.0 to 1.0
    raw_value: Any = None  # Original value before normalization
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'value': self.value,
            'raw_value': self.raw_value,
            'metadata': self.metadata
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
    def evaluate(self, text: str) -> DimensionScore:
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
    def evaluate(self, text: str) -> ProngResult:
        """Evaluate text using this prong."""
        pass

