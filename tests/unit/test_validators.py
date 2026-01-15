"""
Unit tests for validators module.

Tests cover:
- Reddit URL validation and parsing
- Subreddit and post ID validation
- Content length validation
- Script and title validation
- Utility functions (sanitize, truncate, extract)
"""

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

# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(is_valid=True, value="test")
        assert result.is_valid is True
        assert result.value == "test"
        assert result.error is None

    def test_invalid_result(self):
        """Test creating an invalid result."""
        result = ValidationResult(is_valid=False, error="Error message")
        assert result.is_valid is False
        assert result.error == "Error message"

    def test_result_with_details(self):
        """Test result with additional details."""
        result = ValidationResult(
            is_valid=True,
            value="test",
            details={"length": 4},
        )
        assert result.details["length"] == 4

    def test_bool_conversion_valid(self):
        """Test boolean conversion for valid result."""
        result = ValidationResult(is_valid=True)
        assert bool(result) is True

    def test_bool_conversion_invalid(self):
        """Test boolean conversion for invalid result."""
        result = ValidationResult(is_valid=False)
        assert bool(result) is False

    def test_if_statement_usage(self):
        """Test using result in if statement."""
        valid = ValidationResult(is_valid=True, value="test")
        invalid = ValidationResult(is_valid=False, error="error")

        if valid:
            passed = True
        else:
            passed = False
        assert passed is True

        if invalid:
            passed = True
        else:
            passed = False
        assert passed is False


# =============================================================================
# Reddit URL Validation Tests
# =============================================================================


class TestIsValidRedditUrl:
    """Tests for is_valid_reddit_url function."""

    def test_standard_url(self):
        """Test standard Reddit URL."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"
        assert is_valid_reddit_url(url) is True

    def test_old_reddit_url(self):
        """Test old.reddit.com URL."""
        url = "https://old.reddit.com/r/programming/comments/xyz789/title/"
        assert is_valid_reddit_url(url) is True

    def test_url_without_https(self):
        """Test URL without protocol."""
        url = "reddit.com/r/python/comments/abc123/"
        assert is_valid_reddit_url(url) is True

    def test_short_url(self):
        """Test redd.it short URL."""
        url = "https://redd.it/abc123"
        assert is_valid_reddit_url(url) is True

    def test_share_url(self):
        """Test Reddit share URL format."""
        url = "https://www.reddit.com/r/test/s/abc123xyz"
        assert is_valid_reddit_url(url) is True

    def test_invalid_url_google(self):
        """Test non-Reddit URL."""
        assert is_valid_reddit_url("https://google.com") is False

    def test_invalid_url_empty(self):
        """Test empty string."""
        assert is_valid_reddit_url("") is False

    def test_invalid_url_none(self):
        """Test None value."""
        assert is_valid_reddit_url(None) is False

    def test_invalid_url_partial(self):
        """Test partial Reddit URL."""
        assert is_valid_reddit_url("reddit.com/r/python") is False

    def test_url_with_extra_params(self):
        """Test URL with query parameters."""
        url = "https://reddit.com/r/python/comments/abc123/title/?utm_source=share"
        assert is_valid_reddit_url(url) is True


class TestParseRedditUrl:
    """Tests for parse_reddit_url function."""

    def test_parse_standard_url(self):
        """Test parsing standard Reddit URL."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"
        result = parse_reddit_url(url)

        assert result.is_valid is True
        assert result.value["subreddit"] == "python"
        assert result.value["post_id"] == "abc123"
        assert result.value["format"] == "standard"

    def test_parse_old_reddit_url(self):
        """Test parsing old.reddit.com URL."""
        url = "https://old.reddit.com/r/Programming/comments/XYZ789/title/"
        result = parse_reddit_url(url)

        assert result.is_valid is True
        assert result.value["subreddit"] == "Programming"
        assert result.value["post_id"] == "xyz789"  # Lowercased

    def test_parse_short_url(self):
        """Test parsing redd.it short URL."""
        url = "https://redd.it/abc123"
        result = parse_reddit_url(url)

        assert result.is_valid is True
        assert result.value["subreddit"] is None  # Not available
        assert result.value["post_id"] == "abc123"
        assert result.value["format"] == "short"
        assert result.details is not None

    def test_parse_share_url(self):
        """Test parsing share URL."""
        url = "https://reddit.com/r/test/s/shareId123"
        result = parse_reddit_url(url)

        assert result.is_valid is True
        assert result.value["subreddit"] == "test"
        assert result.value["format"] == "share"

    def test_parse_invalid_url(self):
        """Test parsing invalid URL."""
        result = parse_reddit_url("https://google.com")

        assert result.is_valid is False
        assert result.error is not None
        assert "Invalid Reddit URL" in result.error

    def test_parse_empty_url(self):
        """Test parsing empty URL."""
        result = parse_reddit_url("")

        assert result.is_valid is False
        assert result.error == "URL cannot be empty"

    def test_parse_none_url(self):
        """Test parsing None."""
        result = parse_reddit_url(None)

        assert result.is_valid is False
        assert result.error == "URL cannot be empty"

    def test_parse_url_with_whitespace(self):
        """Test URL with leading/trailing whitespace."""
        url = "  https://reddit.com/r/test/comments/abc123/  "
        result = parse_reddit_url(url)

        assert result.is_valid is True
        assert result.value["subreddit"] == "test"


# =============================================================================
# Subreddit Validation Tests
# =============================================================================


class TestValidateSubredditName:
    """Tests for validate_subreddit_name function."""

    def test_valid_subreddit(self):
        """Test valid subreddit name."""
        result = validate_subreddit_name("python")
        assert result.is_valid is True
        assert result.value == "python"

    def test_valid_with_underscore(self):
        """Test subreddit with underscore."""
        result = validate_subreddit_name("ask_reddit")
        assert result.is_valid is True

    def test_valid_with_numbers(self):
        """Test subreddit with numbers."""
        result = validate_subreddit_name("python3")
        assert result.is_valid is True

    def test_remove_r_prefix(self):
        """Test removing r/ prefix."""
        result = validate_subreddit_name("r/python")
        assert result.is_valid is True
        assert result.value == "python"

    def test_too_short(self):
        """Test subreddit too short."""
        result = validate_subreddit_name("a")
        assert result.is_valid is False
        assert "too short" in result.error

    def test_too_long(self):
        """Test subreddit too long."""
        result = validate_subreddit_name("a" * 25)
        assert result.is_valid is False
        assert "too long" in result.error

    def test_invalid_characters(self):
        """Test subreddit with invalid characters."""
        result = validate_subreddit_name("test-sub")
        assert result.is_valid is False
        assert "letters, numbers, and underscores" in result.error

    def test_starts_with_underscore(self):
        """Test subreddit starting with underscore."""
        result = validate_subreddit_name("_test")
        assert result.is_valid is False
        assert "cannot start with underscore" in result.error

    def test_empty_name(self):
        """Test empty subreddit name."""
        result = validate_subreddit_name("")
        assert result.is_valid is False

    def test_none_name(self):
        """Test None subreddit name."""
        result = validate_subreddit_name(None)
        assert result.is_valid is False


# =============================================================================
# Post ID Validation Tests
# =============================================================================


class TestValidatePostId:
    """Tests for validate_post_id function."""

    def test_valid_post_id(self):
        """Test valid post ID."""
        result = validate_post_id("abc123")
        assert result.is_valid is True
        assert result.value == "abc123"

    def test_valid_post_id_7_chars(self):
        """Test valid 7-character post ID."""
        result = validate_post_id("abc1234")
        assert result.is_valid is True

    def test_uppercase_lowercased(self):
        """Test uppercase is converted to lowercase."""
        result = validate_post_id("ABC123")
        assert result.is_valid is True
        assert result.value == "abc123"

    def test_too_short(self):
        """Test post ID too short."""
        result = validate_post_id("abc")
        assert result.is_valid is False
        assert "too short" in result.error

    def test_too_long(self):
        """Test post ID too long."""
        result = validate_post_id("a" * 15)
        assert result.is_valid is False
        assert "too long" in result.error

    def test_invalid_characters(self):
        """Test post ID with invalid characters."""
        result = validate_post_id("abc-123")
        assert result.is_valid is False

    def test_empty_id(self):
        """Test empty post ID."""
        result = validate_post_id("")
        assert result.is_valid is False

    def test_whitespace_trimmed(self):
        """Test whitespace is trimmed."""
        result = validate_post_id("  abc123  ")
        assert result.is_valid is True
        assert result.value == "abc123"


# =============================================================================
# Content Length Validation Tests
# =============================================================================


class TestValidateContentLength:
    """Tests for validate_content_length function."""

    def test_valid_content(self):
        """Test content within bounds."""
        result = validate_content_length("Hello world", min_length=1, max_length=100)
        assert result.is_valid is True
        assert result.value == "Hello world"
        assert result.details["length"] == 11

    def test_content_too_short(self):
        """Test content below minimum."""
        result = validate_content_length("Hi", min_length=10, max_length=100)
        assert result.is_valid is False
        assert "too short" in result.error

    def test_content_too_long(self):
        """Test content above maximum."""
        result = validate_content_length("a" * 200, min_length=1, max_length=100)
        assert result.is_valid is False
        assert "too long" in result.error

    def test_none_content(self):
        """Test None content."""
        result = validate_content_length(None)
        assert result.is_valid is False
        assert "cannot be None" in result.error

    def test_non_string_content(self):
        """Test non-string content."""
        result = validate_content_length(123)
        assert result.is_valid is False
        assert "must be a string" in result.error

    def test_custom_field_name(self):
        """Test custom field name in error."""
        result = validate_content_length("", min_length=1, field_name="Title")
        assert result.is_valid is False
        assert "Title" in result.error


# =============================================================================
# Script Content Validation Tests
# =============================================================================


class TestValidateScriptContent:
    """Tests for validate_script_content function."""

    def test_valid_script(self):
        """Test valid script."""
        script = "This is a test script with enough words to pass validation checks."
        result = validate_script_content(script, min_words=5, max_words=50)
        assert result.is_valid is True
        assert result.details["word_count"] == 12

    def test_script_too_short(self):
        """Test script with too few words."""
        result = validate_script_content("Short", min_words=10)
        assert result.is_valid is False
        assert "too short" in result.error

    def test_script_too_long(self):
        """Test script with too many words."""
        script = " ".join(["word"] * 100)
        result = validate_script_content(script, max_words=50)
        assert result.is_valid is False
        assert "too long" in result.error

    def test_empty_script(self):
        """Test empty script."""
        result = validate_script_content("")
        assert result.is_valid is False
        assert "cannot be empty" in result.error

    def test_excessive_special_chars(self):
        """Test script with too many special characters."""
        script = "!!@#$%^&*()[]{}|:;<>,.?/" * 10 + " normal words here"
        result = validate_script_content(script, min_words=1)
        assert result.is_valid is False
        assert "special characters" in result.error

    def test_whitespace_trimmed(self):
        """Test script whitespace is trimmed."""
        script = "  This is a test script with padding  "
        result = validate_script_content(script, min_words=1, max_words=100)
        assert result.is_valid is True


# =============================================================================
# YouTube Title Validation Tests
# =============================================================================


class TestValidateYoutubeTitle:
    """Tests for validate_youtube_title function."""

    def test_valid_title(self):
        """Test valid YouTube title."""
        result = validate_youtube_title("My Cool Video Title")
        assert result.is_valid is True
        assert result.value == "My Cool Video Title"

    def test_title_truncated(self):
        """Test title is truncated if too long."""
        long_title = "a" * 150
        result = validate_youtube_title(long_title, max_length=100)
        assert result.is_valid is True
        assert len(result.value) == 100
        assert result.value.endswith("...")

    def test_angle_brackets_removed(self):
        """Test angle brackets are removed."""
        result = validate_youtube_title("Title <with> brackets")
        assert result.is_valid is True
        assert "<" not in result.value
        assert ">" not in result.value

    def test_multiple_spaces_collapsed(self):
        """Test multiple spaces are collapsed."""
        result = validate_youtube_title("Title   with   spaces")
        assert result.is_valid is True
        assert "   " not in result.value

    def test_empty_title(self):
        """Test empty title."""
        result = validate_youtube_title("")
        assert result.is_valid is False
        assert "cannot be empty" in result.error

    def test_title_only_brackets(self):
        """Test title with only brackets."""
        result = validate_youtube_title("<>")
        assert result.is_valid is False
        assert "empty after sanitization" in result.error

    def test_whitespace_trimmed(self):
        """Test whitespace is trimmed."""
        result = validate_youtube_title("  My Title  ")
        assert result.is_valid is True
        assert result.value == "My Title"


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_valid_filename(self):
        """Test already valid filename."""
        assert sanitize_filename("video.mp4") == "video.mp4"

    def test_replace_slashes(self):
        """Test slashes are replaced."""
        assert sanitize_filename("video/part1") == "video_part1"
        assert sanitize_filename("video\\part1") == "video_part1"

    def test_replace_special_chars(self):
        """Test special characters are replaced."""
        result = sanitize_filename("video: part 1")
        assert ":" not in result

    def test_remove_question_marks(self):
        """Test question marks are removed."""
        result = sanitize_filename("video?")
        assert "?" not in result

    def test_empty_filename(self):
        """Test empty filename returns 'untitled'."""
        assert sanitize_filename("") == "untitled"

    def test_truncate_long_filename(self):
        """Test long filename is truncated."""
        long_name = "a" * 300
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) <= 100


class TestExtractUrlsFromText:
    """Tests for extract_urls_from_text function."""

    def test_single_url(self):
        """Test extracting single URL."""
        text = "Check out https://example.com for more info"
        urls = extract_urls_from_text(text)
        assert len(urls) == 1
        assert "https://example.com" in urls[0]

    def test_multiple_urls(self):
        """Test extracting multiple URLs."""
        text = "Visit https://google.com or http://example.com"
        urls = extract_urls_from_text(text)
        assert len(urls) == 2

    def test_no_urls(self):
        """Test text without URLs."""
        text = "This is plain text without any links"
        urls = extract_urls_from_text(text)
        assert len(urls) == 0

    def test_empty_text(self):
        """Test empty text."""
        urls = extract_urls_from_text("")
        assert urls == []

    def test_none_text(self):
        """Test None text."""
        urls = extract_urls_from_text(None)
        assert urls == []


class TestTruncateText:
    """Tests for truncate_text function."""

    def test_no_truncation_needed(self):
        """Test text shorter than max."""
        text = "Short text"
        result = truncate_text(text, max_length=50)
        assert result == "Short text"

    def test_truncation_with_suffix(self):
        """Test truncation adds suffix."""
        text = "This is a very long sentence that needs truncation"
        result = truncate_text(text, max_length=20)
        assert len(result) <= 20
        assert result.endswith("...")

    def test_word_boundary_truncation(self):
        """Test truncation at word boundary."""
        text = "This is a long sentence"
        result = truncate_text(text, max_length=15, word_boundary=True)
        assert result.endswith("...")
        assert " ..." not in result  # No space before ellipsis

    def test_no_word_boundary(self):
        """Test truncation without word boundary."""
        text = "Thisisaverylongword"
        result = truncate_text(text, max_length=10, word_boundary=False)
        assert len(result) == 10

    def test_custom_suffix(self):
        """Test custom suffix."""
        text = "This is a long text"
        result = truncate_text(text, max_length=15, suffix=">>")
        assert result.endswith(">>")

    def test_empty_text(self):
        """Test empty text."""
        result = truncate_text("", max_length=10)
        assert result == ""

    def test_none_text(self):
        """Test None text."""
        result = truncate_text(None, max_length=10)
        assert result == ""

    def test_very_short_max_length(self):
        """Test very short max length."""
        result = truncate_text("Hello world", max_length=3)
        assert len(result) <= 3
