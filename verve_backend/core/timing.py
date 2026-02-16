import functools
import time
from typing import Callable, ParamSpec, TypeVar

import structlog

logger = structlog.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def log_timing(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator that logs execution time of a function to debug logger."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            end_time = time.perf_counter()
            elapsed_time = end_time - start_time
            logger.debug(f"{func.__name__} took {elapsed_time:.4f} seconds")

    return wrapper
