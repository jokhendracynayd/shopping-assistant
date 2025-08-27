"""Centralized logging setup for the application.

Creates console + rotating file handlers and provides helpers to get named loggers. Info and error
logs are separated into different files under `app/log/`.
"""

import json
import logging
import os
from datetime import UTC
from datetime import datetime
from logging.handlers import RotatingFileHandler


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        # include any structured data passed via record.__dict__['extra']
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        # include exception text if present
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int):
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def setup_logging(
    enabled: bool = True, level: int = logging.INFO, log_dir: str = "app/log"
) -> None:
    """Configure root logger with console and file handlers.

    - Console: all logs (INFO+)
    - Info file: INFO and WARNING
    - Error file: ERROR and CRITICAL
    """
    if not enabled:
        # disable all handlers: close them first to avoid ResourceWarning for open files
        root = logging.getLogger()
        for h in list(root.handlers):
            try:
                h.close()
            except Exception:
                pass
        root.handlers = []
        root.setLevel(logging.CRITICAL + 10)
        return

    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return

    formatter = JsonFormatter()

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Info file (INFO and WARNING)
    info_path = os.path.join(log_dir, "info.log")
    info_handler = RotatingFileHandler(
        info_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(MaxLevelFilter(logging.WARNING))
    info_handler.setFormatter(formatter)
    root.addHandler(info_handler)

    # Error file (ERROR+)
    error_path = os.path.join(log_dir, "error.log")
    error_handler = RotatingFileHandler(
        error_path, maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
