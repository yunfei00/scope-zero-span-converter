from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .templates import user_data_directory


_LOGGER_NAME = "scope_zero_span_converter"
_LOG_FILE_NAME = "scope-zero-span-converter.log"
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5


def log_directory() -> Path:
    path = user_data_directory() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def current_log_path() -> Path:
    return log_directory() / _LOG_FILE_NAME


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    file_handler = RotatingFileHandler(
        current_log_path(),
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
    )
    logger.addHandler(file_handler)
    return logger


def get_logger() -> logging.Logger:
    return configure_logging()
