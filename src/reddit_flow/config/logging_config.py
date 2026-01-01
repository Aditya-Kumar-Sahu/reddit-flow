"""
Centralized logging configuration for Reddit-Flow.

This module provides:
- Configurable logging setup with console and file handlers
- Structured JSON logging for production
- Colored console output for development
- Log rotation and retention policies
- Integration with the existing StructuredLogger

Usage:
    from reddit_flow.config.logging_config import configure_logging, get_logger

    # Configure logging at application startup
    configure_logging(level="INFO", json_logs=False)

    # Get a logger for your module
    logger = get_logger(__name__)
    logger.info("Application started")
"""

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional


# =============================================================================
# Constants
# =============================================================================

DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "reddit_flow.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


# =============================================================================
# Custom Formatters
# =============================================================================


class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs log records as JSON objects for easy parsing by log aggregation tools.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        return json.dumps(log_data, default=str)


class ColoredFormatter(logging.Formatter):
    """
    Colored formatter for console output during development.

    Uses ANSI escape codes for colorized log levels.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt or DEFAULT_LOG_FORMAT, datefmt or DEFAULT_DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        # Only colorize if output is a terminal
        if sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, "")
            record.levelname = f"{color}{record.levelname}{self.RESET}"

        return super().format(record)


# =============================================================================
# Logger Configuration
# =============================================================================


def configure_logging(
    level: str = "INFO",
    log_dir: str = DEFAULT_LOG_DIR,
    log_file: str = DEFAULT_LOG_FILE,
    json_logs: bool = False,
    console_output: bool = True,
    file_output: bool = True,
) -> None:
    """
    Configure application-wide logging.

    This function sets up logging handlers for console and file output,
    with support for both human-readable and JSON formats.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory for log files.
        log_file: Name of the log file.
        json_logs: If True, use JSON format for file logs.
        console_output: If True, output logs to console.
        file_output: If True, output logs to file.

    Example:
        >>> configure_logging(level="DEBUG", json_logs=True)
        >>> logger = get_logger(__name__)
        >>> logger.info("Logging configured")
    """
    # Get the root logger
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers.clear()

    # Set log level from environment or parameter
    log_level = getattr(logging, os.getenv("LOG_LEVEL", level).upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        # Use colored formatter for console in development
        if not json_logs and sys.stdout.isatty():
            console_handler.setFormatter(ColoredFormatter())
        else:
            console_handler.setFormatter(
                logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
            )

        root_logger.addHandler(console_handler)

    # File handler with rotation
    if file_output:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path / log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)

        # Use JSON formatter for file logs if requested
        if json_logs:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
            )

        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    _configure_library_loggers()

    logging.info("Logging configured: level=%s, json=%s", level, json_logs)


def _configure_library_loggers() -> None:
    """Configure logging levels for third-party libraries to reduce noise."""
    noisy_loggers = [
        "urllib3",
        "requests",
        "httpx",
        "httpcore",
        "asyncio",
        "prawcore",
        "google.auth",
        "google.auth.transport",
        "googleapiclient",
        "telegram",
        "httpx._client",
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    This is a convenience function that returns a properly configured logger.

    Args:
        name: The name for the logger, typically __name__.

    Returns:
        A configured Logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
    """
    return logging.getLogger(name)


# =============================================================================
# Structured Logger (for backward compatibility with existing code)
# =============================================================================


class StructuredLogger:
    """
    Structured JSON logger for workflow step tracking.

    This class maintains backward compatibility with the existing
    StructuredLogger in main.py while providing enhanced functionality.

    Each workflow execution creates a unique log file with structured
    JSON entries for easy parsing and analysis.
    """

    def __init__(self, log_dir: str = DEFAULT_LOG_DIR):
        """
        Initialize the structured logger.

        Args:
            log_dir: Directory for structured log files.
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Create unique log file for this session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"bot_execution_{timestamp}.json"

        # Get standard logger for internal logging
        self._logger = get_logger(__name__)

        # Initialize the file
        self._write_entry(
            {
                "event": "session_start",
                "timestamp": datetime.now().isoformat(),
                "config": {"log_level": logging.getLevelName(logging.root.level)},
            }
        )
        self._logger.info("Structured logging enabled: %s", self.log_file)

    def _write_entry(self, data: Dict[str, Any]) -> None:
        """Write a single JSON entry to the log file."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except Exception as e:
            self._logger.error("Failed to write to structured log: %s", e)

    def log_step(
        self,
        chat_id: int,
        step: int,
        name: str,
        status: str,
        input_data: Any = None,
        output_data: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Log a workflow step.

        Args:
            chat_id: Telegram chat ID.
            step: Step number in the workflow.
            name: Name of the step.
            status: Status of the step (started, completed, failed, etc.).
            input_data: Optional input data for the step.
            output_data: Optional output data from the step.
            error: Optional error message if step failed.
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "event": "step_execution",
            "chat_id": chat_id,
            "step_number": step,
            "step_name": name,
            "status": status,
        }

        if input_data is not None:
            entry["input"] = input_data
        if output_data is not None:
            entry["output"] = output_data
        if error is not None:
            entry["error"] = error

        self._write_entry(entry)

        # Also log to standard logger
        log_msg = f"Step {step} ({name}): {status}"
        if error:
            self._logger.error(log_msg + f" - {error}")
        else:
            self._logger.info(log_msg)
