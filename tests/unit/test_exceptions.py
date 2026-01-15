"""
Unit tests for the exception hierarchy.

Tests for src/reddit_flow/exceptions/errors.py
"""

import pytest

from reddit_flow.exceptions import (
    AIGenerationError,
    APIError,
    ConfigurationError,
    ContentError,
    EmptyContentError,
    InvalidURLError,
    RedditAPIError,
    RedditFlowError,
    RetryableError,
    ScriptGenerationError,
    TransientAPIError,
    TTSError,
    ValidationError,
    VideoGenerationError,
    YouTubeUploadError,
)


class TestRedditFlowError:
    """Tests for the base exception class."""

    def test_basic_creation(self) -> None:
        """Test creating exception with just a message."""
        error = RedditFlowError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.details == {}

    def test_creation_with_details(self) -> None:
        """Test creating exception with details dict."""
        error = RedditFlowError(
            "Operation failed",
            details={"operation": "upload", "retry_count": 3},
        )
        assert error.message == "Operation failed"
        assert error.details == {"operation": "upload", "retry_count": 3}
        assert "Operation failed" in str(error)
        assert "Details:" in str(error)

    def test_is_exception_subclass(self) -> None:
        """Test that RedditFlowError is a proper Exception subclass."""
        error = RedditFlowError("Test error")
        assert isinstance(error, Exception)

        # Test it can be raised and caught
        with pytest.raises(RedditFlowError) as exc_info:
            raise error
        assert exc_info.value.message == "Test error"


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_inherits_from_base(self) -> None:
        """Test inheritance chain."""
        error = ConfigurationError("Missing config")
        assert isinstance(error, RedditFlowError)
        assert isinstance(error, Exception)

    def test_missing_env_var(self) -> None:
        """Test common use case - missing environment variable."""
        error = ConfigurationError(
            "Missing required environment variable",
            details={"variable": "TELEGRAM_BOT_TOKEN"},
        )
        assert "TELEGRAM_BOT_TOKEN" in str(error)

    def test_catch_as_base(self) -> None:
        """Test that ConfigurationError can be caught as base."""
        with pytest.raises(RedditFlowError):
            raise ConfigurationError("Config error")


class TestValidationError:
    """Tests for ValidationError."""

    def test_inherits_from_base(self) -> None:
        """Test inheritance chain."""
        error = ValidationError("Invalid input")
        assert isinstance(error, RedditFlowError)

    def test_invalid_url(self) -> None:
        """Test common use case - invalid URL."""
        error = ValidationError(
            "Invalid Reddit URL format",
            details={"url": "not-a-url", "expected": "reddit.com/r/..."},
        )
        assert error.details["url"] == "not-a-url"


class TestAPIError:
    """Tests for the API error base class."""

    def test_basic_creation(self) -> None:
        """Test creating API error with just message."""
        error = APIError("API call failed")
        assert str(error) == "API call failed"
        assert error.status_code is None
        assert error.response_body is None

    def test_with_status_code(self) -> None:
        """Test API error with HTTP status code."""
        error = APIError(
            "Rate limit exceeded",
            status_code=429,
            details={"retry_after": 60},
        )
        assert "[HTTP 429]" in str(error)
        assert error.status_code == 429

    def test_with_response_body(self) -> None:
        """Test API error with response body."""
        error = APIError(
            "Bad request",
            status_code=400,
            response_body='{"error": "invalid_parameter"}',
        )
        assert error.response_body == '{"error": "invalid_parameter"}'

    def test_inherits_from_base(self) -> None:
        """Test inheritance chain."""
        error = APIError("API error")
        assert isinstance(error, RedditFlowError)


class TestSpecificAPIErrors:
    """Tests for specific API error types."""

    def test_reddit_api_error(self) -> None:
        """Test RedditAPIError."""
        error = RedditAPIError(
            "Post not found",
            status_code=404,
            details={"post_id": "abc123"},
        )
        assert isinstance(error, APIError)
        assert isinstance(error, RedditFlowError)
        assert "[HTTP 404]" in str(error)

    def test_ai_generation_error(self) -> None:
        """Test AIGenerationError."""
        error = AIGenerationError(
            "Token limit exceeded",
            details={"model": "gemini-2.0-flash"},
        )
        assert isinstance(error, APIError)
        assert error.details["model"] == "gemini-2.0-flash"

    def test_tts_error(self) -> None:
        """Test TTSError."""
        error = TTSError(
            "Voice not found",
            details={"voice_id": "invalid_id"},
        )
        assert isinstance(error, APIError)

    def test_video_generation_error(self) -> None:
        """Test VideoGenerationError."""
        error = VideoGenerationError(
            "Generation timed out",
            details={"video_id": "vid_123", "timeout": 1800},
        )
        assert isinstance(error, APIError)
        assert error.details["timeout"] == 1800

    def test_youtube_upload_error(self) -> None:
        """Test YouTubeUploadError."""
        error = YouTubeUploadError(
            "Quota exceeded",
            status_code=403,
            details={"quota_used": 10000},
        )
        assert isinstance(error, APIError)
        assert error.status_code == 403


class TestRetryableError:
    """Tests for RetryableError and TransientAPIError."""

    def test_retryable_error_defaults(self) -> None:
        """Test RetryableError default values."""
        error = RetryableError("Temporary failure")
        assert error.retry_after is None
        assert error.max_retries == 3

    def test_retryable_error_with_timing(self) -> None:
        """Test RetryableError with retry timing."""
        error = RetryableError(
            "Rate limited",
            retry_after=60,
            max_retries=5,
        )
        assert error.retry_after == 60
        assert error.max_retries == 5

    def test_transient_api_error(self) -> None:
        """Test TransientAPIError combines both parent behaviors."""
        error = TransientAPIError(
            "Service unavailable",
            status_code=503,
            retry_after=30,
            max_retries=3,
        )
        # Check APIError attributes
        assert error.status_code == 503
        assert "[HTTP 503]" in str(error)
        # Check RetryableError attributes
        assert error.retry_after == 30
        assert error.max_retries == 3

    def test_transient_api_error_inheritance(self) -> None:
        """Test TransientAPIError inheritance chain."""
        error = TransientAPIError("Temporary error", status_code=429)
        assert isinstance(error, RetryableError)
        assert isinstance(error, APIError)
        assert isinstance(error, RedditFlowError)


class TestContentError:
    """Tests for content-related errors."""

    def test_content_error_base(self) -> None:
        """Test ContentError base class."""
        error = ContentError("Content processing failed")
        assert isinstance(error, RedditFlowError)

    def test_invalid_url_error(self) -> None:
        """Test InvalidURLError."""
        error = InvalidURLError(
            "Not a valid Reddit URL",
            details={"url": "https://example.com"},
        )
        assert isinstance(error, ContentError)
        assert isinstance(error, RedditFlowError)

    def test_empty_content_error(self) -> None:
        """Test EmptyContentError."""
        error = EmptyContentError(
            "No content to process",
            details={"post_id": "abc123", "has_text": False, "comment_count": 0},
        )
        assert isinstance(error, ContentError)
        assert error.details["comment_count"] == 0

    def test_script_generation_error(self) -> None:
        """Test ScriptGenerationError."""
        error = ScriptGenerationError(
            "Script too long",
            details={"word_count": 500, "limit": 200},
        )
        assert isinstance(error, ContentError)
        assert error.details["word_count"] == 500


class TestExceptionHierarchy:
    """Tests for catching exceptions at different hierarchy levels."""

    def test_catch_all_with_base(self) -> None:
        """Test that all exceptions can be caught with base class."""
        exceptions = [
            ConfigurationError("Config error"),
            ValidationError("Validation error"),
            RedditAPIError("Reddit error"),
            AIGenerationError("AI error"),
            TTSError("TTS error"),
            VideoGenerationError("Video error"),
            YouTubeUploadError("YouTube error"),
            TransientAPIError("Transient error"),
            InvalidURLError("URL error"),
            EmptyContentError("Empty error"),
            ScriptGenerationError("Script error"),
        ]

        for exc in exceptions:
            assert isinstance(exc, RedditFlowError)

    def test_catch_api_errors(self) -> None:
        """Test that API errors can be caught with APIError."""
        api_exceptions = [
            RedditAPIError("Reddit error"),
            AIGenerationError("AI error"),
            TTSError("TTS error"),
            VideoGenerationError("Video error"),
            YouTubeUploadError("YouTube error"),
            TransientAPIError("Transient error", status_code=503),
        ]

        for exc in api_exceptions:
            assert isinstance(exc, APIError)

    def test_catch_content_errors(self) -> None:
        """Test that content errors can be caught with ContentError."""
        content_exceptions = [
            InvalidURLError("URL error"),
            EmptyContentError("Empty error"),
            ScriptGenerationError("Script error"),
        ]

        for exc in content_exceptions:
            assert isinstance(exc, ContentError)

    def test_exception_chaining(self) -> None:
        """Test exception chaining works correctly."""
        original = ValueError("Original error")
        wrapped = RedditFlowError("Wrapped error")
        wrapped.__cause__ = original

        try:
            raise wrapped from original
        except RedditFlowError as e:
            assert e.__cause__ is original
