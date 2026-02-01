import contextvars
import logging

import structlog

from verve_backend.core.config import settings

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> str:
    return request_id_context.get() or "-"


def add_logger_name_safe(logger, method_name, event_dict: dict) -> dict:
    """
    Safely adds the logger name to the event dict.
    """
    if logger:
        event_dict["logger"] = logger.name
    else:
        record = event_dict.get("_record")
        if record:
            event_dict["logger"] = record.name
    return event_dict


def setup_logging(log_level: str | int = logging.INFO) -> None:
    """
    Configures Structlog and Standard Logging.

    Follow official docs at https://www.structlog.org/en/stable/standard-library.html#rendering-using-structlog-based-formatters-within-logging
    """

    # 1. Define Processors
    shared_processors = [
        # structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        add_logger_name_safe,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.PROCESS,
                structlog.processors.CallsiteParameter.THREAD,
            ]
        ),
        structlog.processors.dict_tracebacks,
    ]
    # 2. Environment specific formatting
    if settings.ENVIRONMENT == "production" or settings.LOG_FORMAT == "json":
        final_processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        final_processors = shared_processors + [
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    #  Create the Handler that bridges Stdlib -> Structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        ]
        + final_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # 4. Configure Root Logger
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # We need to look at specific Uvicorn loggers and remove their default handlers
    for _log in ["uvicorn", "uvicorn.error"]:
        logger = logging.getLogger(_log)
        logger.handlers = []
        logger.propagate = True
    for _log in ["boto3", "botocore", "s3transfer", "urllib3"]:
        logger = logging.getLogger(_log)
        logger.setLevel(logging.WARNING)
        logger.propagate = False

    # Since we have `verve_backend.access' we mute Uvicorn's default access log entirely
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
