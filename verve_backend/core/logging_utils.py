import contextvars
import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Any

from verve_backend.core.config import settings

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> str:
    return request_id_context.get() or "-"


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings for logs.
    Ideal for production environments (ELK, Datadog, AWS CloudWatch).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "request_id": request_id_context.get(),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "path": record.pathname,
            "line": record.lineno,
            "process": {
                "id": record.process,
                "name": record.processName,
            },
            "thread": {
                "id": record.thread,
                "name": record.threadName,
            },
        }

        # Handle exceptions if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Handle extra fields passed via logger.info(..., extra={...})
        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)  # type: ignore

        return json.dumps(log_obj)


class ConsoleFormatter(logging.Formatter):
    # Standardized format for everything
    format_str = (
        "%(levelname)-8s | "
        "%(asctime)s | "
        "%(request_id)-36s | "
        "%(name)30s:%(lineno)-4d | "
        "%(message)s"
    )

    def format(self, record: logging.LogRecord) -> str:
        # 1. Inject Request ID
        record.request_id = get_request_id()  # type: ignore

        # 2. Shorten Logger Name
        original_name = record.name
        if original_name == "verve_backend":
            record.name = "app"
        elif original_name.startswith("verve_backend."):
            # Remove "verve_backend." prefix (len is 14)
            record.name = original_name[14:]

        # 3. Format
        formatter = logging.Formatter(self.format_str, datefmt="%Y-%m-%d %H:%M:%S")
        formatted_message = formatter.format(record)

        # 4. Restore original name (good practice in case other
        # handlers use this record)
        record.name = original_name

        return formatted_message


def setup_logging() -> None:
    """
    Configures the logging system.
    Intercepts Uvicorn logs and routes them through our handlers.
    """
    formatter_cls = (
        "verve_backend.core.logging_utils.JSONFormatter"
        if settings.LOG_FORMAT == "json"
        else "verve_backend.core.logging_utils.ConsoleFormatter"
    )

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": formatter_cls,
            },
            "access": {
                "()": formatter_cls,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Root logger
            "": {"handlers": ["default"], "level": settings.LOG_LEVEL},
            # Application logger
            "verve_backend": {
                "handlers": ["default"],
                "level": settings.LOG_LEVEL,
                "propagate": False,
            },
            # --- NOISE REDUCTION ---
            # Silence Boto3, Botocore, S3Transfer, Urllib3
            "boto3": {"handlers": ["default"], "level": "WARNING", "propagate": False},
            "botocore": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "s3transfer": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "urllib3": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            # Silence default Uvicorn Access log (we will handle this in middleware now)
            "uvicorn.access": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        },
    }

    logging.config.dictConfig(logging_config)
