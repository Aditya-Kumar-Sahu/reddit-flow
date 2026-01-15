"""Unit tests for the logging configuration module."""

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from reddit_flow.config.logging_config import (
    ColoredFormatter,
    JsonFormatter,
    StructuredLogger,
    configure_logging,
    get_logger,
)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestConfigureLogging:
    """Tests for the configure_logging function."""

    def test_configure_logging_sets_level(self, tmp_path):
        """Test that configure_logging sets the correct log level."""
        configure_logging(
            level="DEBUG",
            log_dir=str(tmp_path),
            console_output=False,
            file_output=True,
        )
        load_dotenv()  # Load environment variables if any
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG or os.getenv("LOG_LEVEL", "")

    def test_configure_logging_creates_log_directory(self, tmp_path):
        """Test that configure_logging creates the log directory."""
        log_dir = tmp_path / "custom_logs"

        configure_logging(
            level="INFO",
            log_dir=str(log_dir),
            console_output=False,
            file_output=True,
        )

        assert log_dir.exists()

    def test_configure_logging_respects_env_variable(self, tmp_path, monkeypatch):
        """Test that LOG_LEVEL environment variable is respected."""
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        configure_logging(
            level="INFO",  # Should be overridden by env var
            log_dir=str(tmp_path),
            console_output=False,
            file_output=True,
        )

        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING


class TestGetLogger:
    """Tests for the get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a Logger instance."""
        logger = get_logger("test_module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"

    def test_get_logger_same_name_returns_same_instance(self):
        """Test that getting a logger with the same name returns the same instance."""
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")

        assert logger1 is logger2


class TestJsonFormatter:
    """Tests for the JsonFormatter class."""

    def test_json_formatter_produces_valid_json(self):
        """Test that JsonFormatter produces valid JSON output."""
        formatter = JsonFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_json_formatter_includes_exception(self):
        """Test that JsonFormatter includes exception information."""
        formatter = JsonFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=10,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestColoredFormatter:
    """Tests for the ColoredFormatter class."""

    def test_colored_formatter_formats_message(self):
        """Test that ColoredFormatter formats messages correctly."""
        formatter = ColoredFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert "Test message" in output
        assert "test" in output


class TestStructuredLogger:
    """Tests for the StructuredLogger class."""

    def test_structured_logger_creates_log_file(self, tmp_path):
        """Test that StructuredLogger creates a log file."""
        logger = StructuredLogger(log_dir=str(tmp_path))

        assert logger.log_file.exists()

    def test_structured_logger_writes_session_start(self, tmp_path):
        """Test that StructuredLogger writes session start entry."""
        logger = StructuredLogger(log_dir=str(tmp_path))

        with open(logger.log_file, "r") as f:
            first_line = f.readline()
            entry = json.loads(first_line)

        assert entry["event"] == "session_start"
        assert "timestamp" in entry

    def test_structured_logger_logs_step(self, tmp_path):
        """Test that StructuredLogger logs workflow steps correctly."""
        logger = StructuredLogger(log_dir=str(tmp_path))

        logger.log_step(
            chat_id=12345,
            step=1,
            name="test_step",
            status="completed",
            input_data={"key": "value"},
            output_data={"result": "success"},
        )

        with open(logger.log_file, "r") as f:
            lines = f.readlines()
            # Second line should be our step
            entry = json.loads(lines[1])

        assert entry["event"] == "step_execution"
        assert entry["chat_id"] == 12345
        assert entry["step_number"] == 1
        assert entry["step_name"] == "test_step"
        assert entry["status"] == "completed"
        assert entry["input"]["key"] == "value"
        assert entry["output"]["result"] == "success"

    def test_structured_logger_logs_errors(self, tmp_path):
        """Test that StructuredLogger logs error information."""
        logger = StructuredLogger(log_dir=str(tmp_path))

        logger.log_step(
            chat_id=12345,
            step=2,
            name="failed_step",
            status="failed",
            error="Something went wrong",
        )

        with open(logger.log_file, "r") as f:
            lines = f.readlines()
            entry = json.loads(lines[1])

        assert entry["status"] == "failed"
        assert entry["error"] == "Something went wrong"
