"""
Custom exception hierarchy for Reddit-Flow.

This module defines all custom exceptions used throughout the application,
organized in a hierarchy that allows for both specific and general error handling.

Exception Hierarchy:
    RedditFlowError (Base)
    ├── ConfigurationError      # Config validation failures
    ├── ValidationError         # Input validation failures
    │
    ├── APIError (Abstract)     # All API-related errors
    │   ├── RedditAPIError      # Reddit API failures
    │   ├── AIGenerationError   # Gemini API failures
    │   ├── TTSError            # ElevenLabs failures
    │   ├── VideoGenerationError# HeyGen failures
    │   └── YouTubeUploadError  # YouTube API failures
    │
    ├── RetryableError          # Errors that should trigger retry
    │   └── TransientAPIError   # Temporary API failures
    │
    └── ContentError            # Content processing errors
        ├── InvalidURLError     # Malformed Reddit URL
        ├── EmptyContentError   # No content to process
        └── ScriptGenerationError# Script creation failed
"""

from typing import Any, Dict, Optional


class RedditFlowError(Exception):
    """
    Base exception for all Reddit-Flow errors.

    All custom exceptions in this application inherit from this class,
    allowing for catch-all error handling when needed.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary with additional error context.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize the exception.

        Args:
            message: Human-readable error description.
            details: Optional dictionary with additional error context.
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(RedditFlowError):
    """
    Raised when required configuration is missing or invalid.

    This exception is raised during application startup when environment
    variables or configuration files are missing or contain invalid values.

    Example:
        >>> raise ConfigurationError(
        ...     "Missing required environment variable",
        ...     details={"variable": "TELEGRAM_BOT_TOKEN"}
        ... )
    """

    pass


class ValidationError(RedditFlowError):
    """
    Raised when input validation fails.

    This exception is raised when user input or data from external sources
    fails validation checks.

    Example:
        >>> raise ValidationError(
        ...     "Invalid Reddit URL format",
        ...     details={"url": "not-a-valid-url", "expected": "reddit.com/r/.../comments/..."}
        ... )
    """

    pass


# =============================================================================
# API Errors
# =============================================================================


class APIError(RedditFlowError):
    """
    Base class for all API-related errors.

    This is an abstract base class for errors that occur when interacting
    with external APIs. Specific API errors should inherit from this class.

    Attributes:
        status_code: HTTP status code if applicable.
        response_body: Raw response body if available.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        """
        Initialize the API error.

        Args:
            message: Human-readable error description.
            details: Optional dictionary with additional error context.
            status_code: HTTP status code if applicable.
            response_body: Raw response body if available.
        """
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        """Return string representation including status code."""
        base = super().__str__()
        if self.status_code:
            return f"[HTTP {self.status_code}] {base}"
        return base


class RedditAPIError(APIError):
    """
    Raised when Reddit API operations fail.

    This exception covers authentication failures, rate limiting,
    post not found errors, and other Reddit-specific issues.

    Example:
        >>> raise RedditAPIError(
        ...     "Post not found",
        ...     details={"subreddit": "technology", "post_id": "abc123"},
        ...     status_code=404
        ... )
    """

    pass


class AIGenerationError(APIError):
    """
    Raised when AI content generation fails.

    This exception is raised when Google Gemini API calls fail,
    including content extraction and script generation.

    Example:
        >>> raise AIGenerationError(
        ...     "Failed to generate script",
        ...     details={"model": "gemini-2.0-flash", "error": "Token limit exceeded"}
        ... )
    """

    pass


class TTSError(APIError):
    """
    Raised when text-to-speech conversion fails.

    This exception covers ElevenLabs API failures including
    voice not found, insufficient credits, and audio generation errors.

    Example:
        >>> raise TTSError(
        ...     "Voice not found",
        ...     details={"voice_id": "invalid_id"}
        ... )
    """

    pass


class VideoGenerationError(APIError):
    """
    Raised when avatar video generation fails.

    This exception covers HeyGen API failures including avatar errors,
    generation timeouts, and video processing failures.

    Example:
        >>> raise VideoGenerationError(
        ...     "Video generation timed out",
        ...     details={"video_id": "vid_123", "timeout": 1800}
        ... )
    """

    pass


class YouTubeUploadError(APIError):
    """
    Raised when YouTube upload fails.

    This exception covers OAuth failures, quota exceeded errors,
    and video upload failures.

    Example:
        >>> raise YouTubeUploadError(
        ...     "Quota exceeded",
        ...     details={"quota_used": 10000, "quota_limit": 10000},
        ...     status_code=403
        ... )
    """

    pass


class MediaGenerationError(APIError):
    """
    Raised when the media generation workflow fails.

    This exception covers failures in the combined audio/video
    generation pipeline that aren't specific to TTS or video generation.

    Example:
        >>> raise MediaGenerationError(
        ...     "Media generation pipeline failed",
        ...     details={"step": "audio_upload", "error": "Network timeout"}
        ... )
    """

    pass


# =============================================================================
# Retryable Errors
# =============================================================================


class RetryableError(RedditFlowError):
    """
    Base class for errors that should trigger automatic retry.

    These errors represent transient failures that may succeed on retry,
    such as network timeouts or temporary service unavailability.

    Attributes:
        retry_after: Suggested wait time before retry (seconds).
        max_retries: Maximum number of retries suggested.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
        max_retries: int = 3,
    ):
        """
        Initialize the retryable error.

        Args:
            message: Human-readable error description.
            details: Optional dictionary with additional error context.
            retry_after: Suggested wait time before retry (seconds).
            max_retries: Maximum number of retries suggested.
        """
        super().__init__(message, details)
        self.retry_after = retry_after
        self.max_retries = max_retries


class TransientAPIError(RetryableError, APIError):
    """
    Raised for temporary API failures that should be retried.

    This exception represents API errors that are likely to be temporary,
    such as rate limiting (429), service unavailable (503), or timeouts.

    Example:
        >>> raise TransientAPIError(
        ...     "Rate limit exceeded",
        ...     status_code=429,
        ...     retry_after=60
        ... )
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        retry_after: Optional[int] = None,
        max_retries: int = 3,
    ):
        """Initialize the transient API error."""
        # Initialize both parent classes
        APIError.__init__(self, message, details, status_code, response_body)
        self.retry_after = retry_after
        self.max_retries = max_retries


# =============================================================================
# Content Errors
# =============================================================================


class ContentError(RedditFlowError):
    """
    Base class for content processing errors.

    These errors occur during content extraction, transformation,
    or validation stages of the workflow.
    """

    pass


class InvalidURLError(ContentError):
    """
    Raised when a malformed or invalid URL is provided.

    Example:
        >>> raise InvalidURLError(
        ...     "Invalid Reddit URL",
        ...     details={"url": "https://not-reddit.com/post"}
        ... )
    """

    pass


class EmptyContentError(ContentError):
    """
    Raised when there is no content to process.

    This can occur when a Reddit post has been deleted, has no text,
    or has no comments to include.

    Example:
        >>> raise EmptyContentError(
        ...     "Post has no content",
        ...     details={"post_id": "abc123", "has_text": False, "comment_count": 0}
        ... )
    """

    pass


class ScriptGenerationError(ContentError):
    """
    Raised when script generation fails.

    This can occur when the AI fails to generate a valid script,
    or when the script doesn't meet quality requirements.

    Example:
        >>> raise ScriptGenerationError(
        ...     "Generated script exceeds word limit",
        ...     details={"word_count": 500, "limit": 200}
        ... )
    """

    pass
