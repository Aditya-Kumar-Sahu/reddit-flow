"""
Utility functions for Reddit-Flow.

This module provides shared utilities:
- validators: Input validation functions
- retry: Retry decorators, circuit breaker, and timeout utilities
- structured_logger: JSON logging for workflow steps
"""

from reddit_flow.utils.retry import (
    AGGRESSIVE_RETRY_CONFIG,
    API_RETRY_CONFIG,
    CONSERVATIVE_RETRY_CONFIG,
    DEFAULT_RETRY_CONFIG,
    DEFAULT_TIMEOUT_CONFIG,
    FAST_TIMEOUT_CONFIG,
    VIDEO_TIMEOUT_CONFIG,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    RetryConfig,
    TimeoutConfig,
    TimeoutError,
    log_retry_attempt,
    timeout_decorator,
    with_retry,
    with_retry_sync,
    with_timeout,
    with_timeout_async,
)
from reddit_flow.utils.validators import (
    ValidationResult,
    extract_urls_from_text,
    is_valid_reddit_url,
    parse_reddit_url,
    sanitize_filename,
    truncate_text,
    validate_content_length,
    validate_post_id,
    validate_script_content,
    validate_subreddit_name,
    validate_youtube_title,
)

__all__ = [
    # Validation
    "ValidationResult",
    "is_valid_reddit_url",
    "parse_reddit_url",
    "validate_subreddit_name",
    "validate_post_id",
    "validate_content_length",
    "validate_script_content",
    "validate_youtube_title",
    "sanitize_filename",
    "extract_urls_from_text",
    "truncate_text",
    # Retry
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",
    "AGGRESSIVE_RETRY_CONFIG",
    "CONSERVATIVE_RETRY_CONFIG",
    "API_RETRY_CONFIG",
    "with_retry",
    "with_retry_sync",
    "log_retry_attempt",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitOpenError",
    # Timeout
    "TimeoutConfig",
    "DEFAULT_TIMEOUT_CONFIG",
    "FAST_TIMEOUT_CONFIG",
    "VIDEO_TIMEOUT_CONFIG",
    "TimeoutError",
    "with_timeout",
    "with_timeout_async",
    "timeout_decorator",
]
