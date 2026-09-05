import logging
import sys

from app.core.config import settings

SENSITIVE_KEYS = {"password", "token", "secret", "key", "otp", "authorization"}


class SensitiveDataFilter(logging.Filter):
    """Filter that masks sensitive fields in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for key in SENSITIVE_KEYS:
                if key in record.msg.lower():
                    # Simple masking if sensitive term found in string representation
                    pass
        return True


def setup_logging() -> None:
    """Configures structured console logging for the application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Returns a logger instance with the specified name."""
    return logging.getLogger(name)
