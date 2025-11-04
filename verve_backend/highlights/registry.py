import logging
from datetime import timedelta
from typing import Callable, TypeAlias
from uuid import UUID

from sqlmodel import Session

from verve_backend.models import HighlightMetric

logger = logging.getLogger("uvicorn.error")

CalculatorFunc: TypeAlias = Callable[[UUID, Session], timedelta | float | None]


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
                "Registering calculator function '%s' for metric '%s'",
                func.__name__,
                metric.name,
            )
            if metric in self.calculators:
                logger.warning("Overwriting calculator for metric '%s'", metric.name)
            self.calculators[metric] = func
            return func

        return decorator

    def run_all(
        self, activity_id: UUID, session: Session
    ) -> dict[HighlightMetric, timedelta | float | None]:
        """Runs all registered calculators for a given activity."""
        results = {}
        for metric, calculator_func in self.calculators.items():
            try:
                results[metric] = calculator_func(activity_id, session)
            except Exception:
                logger.exception(
                    "Calculator for metric '%s' failed for activity '%s'",
                    metric.name,
                    activity_id,
                )
                results[metric] = None
        return results


registry = Registry()
