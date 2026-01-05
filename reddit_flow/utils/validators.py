"""
Input validation utilities for Reddit-Flow.

This module provides reusable validation functions for:
- Reddit URLs and identifiers
- Content validation (length, format)
- Script and title validation
- General input sanitization
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from reddit_flow.config import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """
    Result of a validation operation.

    Attributes:
        is_valid: Whether the validation passed.
        value: The validated/cleaned value (if valid).
        error: Error message (if invalid).
        details: Additional validation details.
    """

    is_valid: bool
    value: Any = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        """Allow ValidationResult to be used in boolean context."""
        return self.is_valid


# =============================================================================
# Reddit URL Validation
# =============================================================================

# Pattern for standard Reddit URLs
REDDIT_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:old\.)?reddit\.com/r/([a-zA-Z0-9_]+)/comments/([a-z0-9]+)",
    re.IGNORECASE,
)

# Pattern for short Reddit URLs (redd.it)
REDDIT_SHORT_URL_PATTERN = re.compile(
    r"(?:https?://)?redd\.it/([a-z0-9]+)",
    re.IGNORECASE,
)

# Pattern for Reddit share URLs
REDDIT_SHARE_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?reddit\.com/r/([a-zA-Z0-9_]+)/s/([a-zA-Z0-9]+)",
    re.IGNORECASE,
)

# Subreddit name validation pattern
SUBREDDIT_PATTERN = re.compile(r"^[a-zA-Z0-9_]{2,21}$")

# Post ID validation pattern (base36)
POST_ID_PATTERN = re.compile(r"^[a-z0-9]{5,10}$", re.IGNORECASE)


def is_valid_reddit_url(url: str) -> bool:
    """
    Check if a string is a valid Reddit URL.

    Supports multiple Reddit URL formats:
    - https://www.reddit.com/r/subreddit/comments/postid/...
    - https://old.reddit.com/r/subreddit/comments/postid/...
    - https://redd.it/postid

    Args:
        url: URL string to validate.

    Returns:
        True if URL is a valid Reddit URL format.

    Example:
        >>> is_valid_reddit_url("https://reddit.com/r/python/comments/abc123/")
        True
        >>> is_valid_reddit_url("https://google.com")
        False
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()

    # Check standard Reddit URL
    if REDDIT_URL_PATTERN.search(url):
        return True

    # Check short URL
    if REDDIT_SHORT_URL_PATTERN.search(url):
        return True

    # Check share URL
    if REDDIT_SHARE_URL_PATTERN.search(url):
        return True

    return False


def parse_reddit_url(url: str) -> ValidationResult:
    """
    Parse a Reddit URL and extract subreddit and post ID.

    Supports multiple URL formats and returns a ValidationResult
    with the parsed components.

    Args:
        url: Reddit URL to parse.

    Returns:
        ValidationResult with parsed data or error message.

    Example:
        >>> result = parse_reddit_url("https://reddit.com/r/python/comments/abc123/")
        >>> result.is_valid
        True
        >>> result.value
        {'subreddit': 'python', 'post_id': 'abc123', 'url': '...'}
    """
    if not url or not isinstance(url, str):
        return ValidationResult(
            is_valid=False,
            error="URL cannot be empty",
        )

    url = url.strip()

    # Try standard Reddit URL
    match = REDDIT_URL_PATTERN.search(url)
    if match:
        subreddit, post_id = match.groups()
        return ValidationResult(
            is_valid=True,
            value={
                "subreddit": subreddit,
                "post_id": post_id.lower(),
                "url": url,
                "format": "standard",
            },
        )

    # Try short URL (redd.it) - note: doesn't include subreddit
    match = REDDIT_SHORT_URL_PATTERN.search(url)
    if match:
        post_id = match.group(1)
        return ValidationResult(
            is_valid=True,
            value={
                "subreddit": None,  # Not available in short URL
                "post_id": post_id.lower(),
                "url": url,
                "format": "short",
            },
            details={"note": "Subreddit must be resolved from API"},
        )

    # Try share URL
    match = REDDIT_SHARE_URL_PATTERN.search(url)
    if match:
        subreddit, share_id = match.groups()
        return ValidationResult(
            is_valid=True,
            value={
                "subreddit": subreddit,
                "post_id": share_id,  # Share ID, may need resolution
                "url": url,
                "format": "share",
            },
            details={"note": "Share URL may require redirect resolution"},
        )

    return ValidationResult(
        is_valid=False,
        error="Invalid Reddit URL. Expected: https://reddit.com/r/subreddit/comments/postid/",
    )


def validate_subreddit_name(name: str) -> ValidationResult:
    """
    Validate a subreddit name.

    Rules:
    - Must be 2-21 characters
    - Alphanumeric and underscores only
    - Cannot start with underscore

    Args:
        name: Subreddit name to validate.

    Returns:
        ValidationResult with cleaned name or error.

    Example:
        >>> validate_subreddit_name("python")
        ValidationResult(is_valid=True, value='python', ...)
        >>> validate_subreddit_name("a")
        ValidationResult(is_valid=False, error='...too short...', ...)
    """
    if not name or not isinstance(name, str):
        return ValidationResult(
            is_valid=False,
            error="Subreddit name cannot be empty",
        )

    # Remove r/ prefix if present
    name = name.strip()
    if name.startswith("r/"):
        name = name[2:]

    # Check length
    if len(name) < 2:
        return ValidationResult(
            is_valid=False,
            error="Subreddit name too short (minimum 2 characters)",
        )
    if len(name) > 21:
        return ValidationResult(
            is_valid=False,
            error="Subreddit name too long (maximum 21 characters)",
        )

    # Check pattern
    if not SUBREDDIT_PATTERN.match(name):
        return ValidationResult(
            is_valid=False,
            error="Subreddit name can only contain letters, numbers, and underscores",
        )

    # Check doesn't start with underscore
    if name.startswith("_"):
        return ValidationResult(
            is_valid=False,
            error="Subreddit name cannot start with underscore",
        )

    return ValidationResult(
        is_valid=True,
        value=name,
    )


def validate_post_id(post_id: str) -> ValidationResult:
    """
    Validate a Reddit post ID.

    Reddit post IDs are base36 encoded strings, typically 5-7 characters.

    Args:
        post_id: Post ID to validate.

    Returns:
        ValidationResult with cleaned ID or error.

    Example:
        >>> validate_post_id("abc123")
        ValidationResult(is_valid=True, value='abc123', ...)
        >>> validate_post_id("INVALID!")
        ValidationResult(is_valid=False, error='...', ...)
    """
    if not post_id or not isinstance(post_id, str):
        return ValidationResult(
            is_valid=False,
            error="Post ID cannot be empty",
        )

    post_id = post_id.strip().lower()

    if len(post_id) < 5:
        return ValidationResult(
            is_valid=False,
            error="Post ID too short (minimum 5 characters)",
        )
    if len(post_id) > 10:
        return ValidationResult(
            is_valid=False,
            error="Post ID too long (maximum 10 characters)",
        )

    if not POST_ID_PATTERN.match(post_id):
        return ValidationResult(
            is_valid=False,
            error="Post ID can only contain lowercase letters and numbers",
        )

    return ValidationResult(
        is_valid=True,
        value=post_id,
    )


# =============================================================================
# Content Validation
# =============================================================================


def validate_content_length(
    content: str,
    min_length: int = 1,
    max_length: int = 100000,
    field_name: str = "Content",
) -> ValidationResult:
    """
    Validate content length is within bounds.

    Args:
        content: Text content to validate.
        min_length: Minimum allowed length.
        max_length: Maximum allowed length.
        field_name: Name for error messages.

    Returns:
        ValidationResult with content or error.

    Example:
        >>> validate_content_length("Hello", min_length=1, max_length=100)
        ValidationResult(is_valid=True, value='Hello', ...)
    """
    if content is None:
        return ValidationResult(
            is_valid=False,
            error=f"{field_name} cannot be None",
        )

    if not isinstance(content, str):
        return ValidationResult(
            is_valid=False,
            error=f"{field_name} must be a string",
        )

    length = len(content)

    if length < min_length:
        return ValidationResult(
            is_valid=False,
            error=f"{field_name} too short (minimum {min_length} characters, got {length})",
            details={"length": length, "min_length": min_length},
        )

    if length > max_length:
        return ValidationResult(
            is_valid=False,
            error=f"{field_name} too long (maximum {max_length} characters, got {length})",
            details={"length": length, "max_length": max_length},
        )

    return ValidationResult(
        is_valid=True,
        value=content,
        details={"length": length},
    )


def validate_script_content(
    script: str,
    min_words: int = 10,
    max_words: int = 500,
) -> ValidationResult:
    """
    Validate script content for video generation.

    Checks:
    - Not empty
    - Word count within bounds
    - No excessive special characters

    Args:
        script: Script text to validate.
        min_words: Minimum word count.
        max_words: Maximum word count.

    Returns:
        ValidationResult with script details or error.

    Example:
        >>> validate_script_content("This is a test script for validation.")
        ValidationResult(is_valid=True, value='...', details={'word_count': 7})
    """
    if not script or not isinstance(script, str):
        return ValidationResult(
            is_valid=False,
            error="Script cannot be empty",
        )

    script = script.strip()
    words = script.split()
    word_count = len(words)

    if word_count < min_words:
        return ValidationResult(
            is_valid=False,
            error=f"Script too short (minimum {min_words} words, got {word_count})",
            details={"word_count": word_count, "min_words": min_words},
        )

    if word_count > max_words:
        return ValidationResult(
            is_valid=False,
            error=f"Script too long (maximum {max_words} words, got {word_count})",
            details={"word_count": word_count, "max_words": max_words},
        )

    # Check for excessive special characters (potential injection)
    special_char_ratio = sum(1 for c in script if not c.isalnum() and not c.isspace()) / len(script)
    if special_char_ratio > 0.3:
        return ValidationResult(
            is_valid=False,
            error="Script contains too many special characters",
            details={"special_char_ratio": special_char_ratio},
        )

    return ValidationResult(
        is_valid=True,
        value=script,
        details={
            "word_count": word_count,
            "char_count": len(script),
        },
    )


def validate_youtube_title(
    title: str,
    max_length: int = 100,
) -> ValidationResult:
    """
    Validate and sanitize a YouTube video title.

    YouTube title rules:
    - Maximum 100 characters
    - No angle brackets < >
    - No excessive special characters

    Args:
        title: Title to validate.
        max_length: Maximum allowed length (default 100 for YouTube).

    Returns:
        ValidationResult with sanitized title or error.

    Example:
        >>> validate_youtube_title("My Cool Video Title")
        ValidationResult(is_valid=True, value='My Cool Video Title', ...)
    """
    if not title or not isinstance(title, str):
        return ValidationResult(
            is_valid=False,
            error="Title cannot be empty",
        )

    title = title.strip()

    if len(title) > max_length:
        # Truncate and add ellipsis
        title = title[: max_length - 3] + "..."
        logger.debug(f"Title truncated to {max_length} characters")

    # Remove angle brackets (not allowed by YouTube)
    title = re.sub(r"[<>]", "", title)

    # Remove multiple consecutive spaces
    title = re.sub(r"\s+", " ", title)

    if not title:
        return ValidationResult(
            is_valid=False,
            error="Title is empty after sanitization",
        )

    return ValidationResult(
        is_valid=True,
        value=title,
        details={"length": len(title)},
    )


# =============================================================================
# General Utilities
# =============================================================================


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a string for use as a filename.

    Removes/replaces characters that are invalid in filenames.

    Args:
        filename: Original filename.
        max_length: Maximum filename length.

    Returns:
        Sanitized filename string.

    Example:
        >>> sanitize_filename("My Video: Part 1/2")
        'My Video_ Part 1_2'
    """
    if not filename:
        return "untitled"

    # Replace common problematic characters
    replacements = {
        "/": "_",
        "\\": "_",
        ":": "_",
        "*": "_",
        "?": "",
        '"': "'",
        "<": "",
        ">": "",
        "|": "_",
    }

    for char, replacement in replacements.items():
        filename = filename.replace(char, replacement)

    # Remove control characters
    filename = "".join(c for c in filename if ord(c) >= 32)

    # Truncate if needed
    if len(filename) > max_length:
        filename = filename[: max_length - 3] + "..."

    return filename.strip() or "untitled"


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from a text string.

    Args:
        text: Text to search for URLs.

    Returns:
        List of found URLs.

    Example:
        >>> extract_urls_from_text("Check out https://reddit.com and https://google.com")
        ['https://reddit.com', 'https://google.com']
    """
    if not text:
        return []

    url_pattern = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")
    return url_pattern.findall(text)


def truncate_text(
    text: str,
    max_length: int,
    suffix: str = "...",
    word_boundary: bool = True,
) -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: Text to truncate.
        max_length: Maximum length including suffix.
        suffix: String to append when truncated.
        word_boundary: If True, truncate at word boundary.

    Returns:
        Truncated text.

    Example:
        >>> truncate_text("This is a long sentence", 15)
        'This is a...'
    """
    if not text or len(text) <= max_length:
        return text or ""

    truncate_at = max_length - len(suffix)
    if truncate_at <= 0:
        return suffix[:max_length]

    truncated = text[:truncate_at]

    if word_boundary:
        # Find last space
        last_space = truncated.rfind(" ")
        if last_space > truncate_at // 2:  # Only if it's not too early
            truncated = truncated[:last_space]

    return truncated.rstrip() + suffix
