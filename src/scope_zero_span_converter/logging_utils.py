from __future__ import annotations

import logging
from pathlib import Path

from .templates import user_data_directory


_LOGGER_NAME = "scope_zero_span_converter"


def log_directory() -> Path:
    path = user_data_directory() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    file_handler = logging.FileHandler(
        log_directory() / "scope-zero-span-converter.log",
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
