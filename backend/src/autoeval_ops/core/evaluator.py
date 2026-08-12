"""Base class and result model shared by every evaluator."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationResult:
    metric_name: str
    metric_value: float
    status: str  # "pass" | "fail" | "warning"
    details: dict[str, Any] = field(default_factory=dict)


class Evaluator(ABC):
    """Every evaluator (correctness, toxicity, etc.) implements this."""

    name: str = "base"

    @abstractmethod
    async def evaluate(self, output: str, **kwargs: Any) -> EvaluationResult:
        """Evaluate a single model output and return a result."""
        raise NotImplementedError