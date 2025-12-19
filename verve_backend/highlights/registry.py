import logging
from dataclasses import dataclass
from typing import Callable, TypeAlias
from uuid import UUID

from sqlmodel import Session

from verve_backend.models import HighlightMetric

logger = logging.getLogger(__name__)


@dataclass
class CalculatorResult:
    value: int | float
    track_id: int | None = None


CalculatorFunc: TypeAlias = Callable[[UUID, UUID, Session], CalculatorResult | None]


class Registry:
    def __init__(
        self, standard_calculators: dict[HighlightMetric, CalculatorFunc] | None = None
    ) -> None:
        self.calculators: dict[HighlightMetric, CalculatorFunc] = {}

        if standard_calculators:
            for metric, function in standard_calculators.items():
                self.add(metric)(function)

    def add(
        self, metric: HighlightMetric
    ) -> Callable[[CalculatorFunc], CalculatorFunc]:
        """A decorator to register a calculator function for a given metric."""

        def decorator(func: CalculatorFunc) -> CalculatorFunc:
            logger.debug(
                "Registering calculator function for metric '%s'",
                metric.name,
            )
            if metric in self.calculators:
                logger.warning("Overwriting calculator for metric '%s'", metric.name)
            self.calculators[metric] = func
            return func

        return decorator

    def run_all(
        self, activity_id: UUID, user_id: UUID, session: Session
    ) -> dict[HighlightMetric, CalculatorResult | None]:
        """Runs all registered calculators for a given activity."""
        results = {}
        for metric, calculator_func in self.calculators.items():
            try:
                results[metric] = calculator_func(activity_id, user_id, session)
            except Exception:
                logger.exception(
                    "Calculator for metric '%s' failed for activity '%s' (user %s)",
                    metric.name,
                    activity_id,
                    user_id,
                )
                results[metric] = None
        return results


registry = Registry()
