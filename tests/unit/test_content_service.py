"""
Unit tests for ContentService.

Tests cover:
- URL parsing (various formats)
- URL validation
- Post content fetching
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from reddit_flow.exceptions import ContentError, EmptyContentError, InvalidURLError, RedditAPIError
from reddit_flow.models import LinkInfo, RedditComment, RedditPost
from reddit_flow.services.content_service import ContentService


class TestContentServiceInitialization:
    """Tests for ContentService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        with patch("reddit_flow.services.content_service.RedditClient"):
            service = ContentService()

        assert service._max_comments == 50
        assert service._reddit_client is None  # Lazy loaded

    def test_init_with_custom_max_comments(self):
        """Test initialization with custom max comments."""
        service = ContentService(max_comments=100)

        assert service._max_comments == 100

    def test_init_with_reddit_client(self):
        """Test initialization with provided Reddit client."""
        mock_client = MagicMock()
        service = ContentService(reddit_client=mock_client)

        assert service._reddit_client is mock_client
        assert service.reddit_client is mock_client

    def test_lazy_load_reddit_client(self):
        """Test that Reddit client is lazy loaded on first access."""
        with patch("reddit_flow.services.content_service.RedditClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            service = ContentService()

            # Client not created yet
            assert service._reddit_client is None

            # Access triggers creation
            client = service.reddit_client

            assert client is mock_instance
            MockClient.assert_called_once()


class TestContentServiceURLParsing:
    """Tests for Reddit URL parsing."""

    @pytest.fixture
    def service(self):
        """Create a ContentService with mocked Reddit client."""
        return ContentService(reddit_client=MagicMock())

    @pytest.mark.parametrize(
        "url,expected_subreddit,expected_post_id",
        [
            (
                "https://www.reddit.com/r/python/comments/abc123/some_title/",
                "python",
                "abc123",
            ),
            (
                "https://reddit.com/r/AskReddit/comments/xyz789/question/",
                "AskReddit",
                "xyz789",
            ),
            (
                "https://old.reddit.com/r/programming/comments/def456/",
                "programming",
                "def456",
            ),
            (
                "http://www.reddit.com/r/test_sub/comments/test12/",
                "test_sub",
                "test12",
            ),
            # With query parameters
            (
                "https://www.reddit.com/r/python/comments/abc123/?utm_source=share",
                "python",
                "abc123",
            ),
        ],
    )
    def test_parse_standard_urls(self, service, url, expected_subreddit, expected_post_id):
        """Test parsing various standard Reddit URL formats."""
        result = service.parse_reddit_url(url)

        assert isinstance(result, LinkInfo)
        assert result.subreddit == expected_subreddit
        assert result.post_id == expected_post_id
        assert result.link == url

    def test_parse_short_url_raises_error(self, service):
        """Test that short redd.it URLs raise InvalidURLError."""
        url = "https://redd.it/abc123"

        with pytest.raises(InvalidURLError) as exc_info:
            service.parse_reddit_url(url)

        assert "Short URLs" in str(exc_info.value)

    def test_parse_invalid_url_raises_error(self, service):
        """Test that invalid URLs raise InvalidURLError."""
        invalid_urls = [
            "https://www.google.com/search",
            "not a url",
            "https://twitter.com/user/status/123",
            "",
        ]

        for url in invalid_urls:
            with pytest.raises(InvalidURLError):
                service.parse_reddit_url(url)


class TestContentServiceURLValidation:
    """Tests for URL component validation."""

    @pytest.fixture
    def service(self):
        """Create a ContentService with mocked Reddit client."""
        return ContentService(reddit_client=MagicMock())

    @pytest.mark.parametrize(
        "subreddit,post_id,expected",
        [
            ("python", "abc123", True),
            ("AskReddit", "xyz789", True),
            ("test_sub", "ab12", True),
            (None, "abc123", True),  # Short URL case
            # Invalid cases
            ("python", "", False),
            ("python", None, False),
            ("python", "a", False),  # Too short
            ("python", "abc123xyz789", False),  # Too long
            ("ab", "abc123", True),  # Subreddit min length
            ("a", "abc123", False),  # Subreddit too short
        ],
    )
    def test_validate_url(self, service, subreddit, post_id, expected):
        """Test URL component validation."""
        result = service.validate_url(subreddit, post_id)
        assert result is expected


class TestContentServiceFetchContent:
    """Tests for fetching post content."""

    @pytest.fixture
    def mock_reddit_client(self):
        """Create a mock Reddit client."""
        client = MagicMock()
        client.get_post_data.return_value = {
            "id": "abc123",
            "title": "Test Post Title",
            "selftext": "This is the post content.",
            "author": "test_user",
            "score": 100,
            "url": "https://reddit.com/r/test/comments/abc123/",
            "num_comments": 5,
            "created_utc": 1704067200.0,
            "comments": [
                {
                    "id": "comment1",
                    "author": "commenter1",
                    "body": "First comment",
                    "score": 50,
                    "created_utc": 1704067300.0,
                },
                {
                    "id": "comment2",
                    "author": "commenter2",
                    "body": "Second comment",
                    "score": 30,
                    "created_utc": 1704067400.0,
                },
            ],
        }
        return client

    @pytest.fixture
    def service(self, mock_reddit_client):
        """Create a ContentService with mocked Reddit client."""
        return ContentService(reddit_client=mock_reddit_client)

    def test_get_post_content_success(self, service, mock_reddit_client):
        """Test successful post content fetching."""
        result = service.get_post_content("test", "abc123")

        assert isinstance(result, RedditPost)
        assert result.id == "abc123"
        assert result.title == "Test Post Title"
        assert result.selftext == "This is the post content."
        assert result.author == "test_user"
        assert result.score == 100
        assert len(result.comments) == 2

        mock_reddit_client.get_post_data.assert_called_once_with("test", "abc123")

    def test_get_post_content_with_comments(self, service):
        """Test that comments are properly converted to models."""
        result = service.get_post_content("test", "abc123")

        assert len(result.comments) == 2
        assert all(isinstance(c, RedditComment) for c in result.comments)
        assert result.comments[0].author == "commenter1"
        assert result.comments[0].body == "First comment"
        assert result.comments[0].score == 50

    def test_get_post_content_without_comments(self, service, mock_reddit_client):
        """Test fetching without comments."""
        result = service.get_post_content("test", "abc123", include_comments=False)

        assert isinstance(result, RedditPost)
        assert len(result.comments) == 0

    def test_get_post_content_max_comments(self, mock_reddit_client):
        """Test that max_comments limit is respected."""
        # Add more comments
        mock_reddit_client.get_post_data.return_value["comments"] = [
            {"id": f"comment{i}", "author": f"user{i}", "body": f"Comment {i}", "score": i}
            for i in range(100)
        ]

        service = ContentService(reddit_client=mock_reddit_client, max_comments=10)
        result = service.get_post_content("test", "abc123")

        assert len(result.comments) == 10

    def test_get_post_content_api_error(self, service, mock_reddit_client):
        """Test handling of Reddit API errors."""
        mock_reddit_client.get_post_data.side_effect = RedditAPIError("API failed")

        with pytest.raises(RedditAPIError):
            service.get_post_content("test", "abc123")

    def test_get_post_content_generic_error(self, service, mock_reddit_client):
        """Test handling of generic errors."""
        mock_reddit_client.get_post_data.side_effect = ValueError("Unexpected error")

        with pytest.raises(ContentError):
            service.get_post_content("test", "abc123")


class TestContentServiceGetContentFromURL:
    """Tests for get_content_from_url method."""

    @pytest.fixture
    def mock_reddit_client(self):
        """Create a mock Reddit client."""
        client = MagicMock()
        client.get_post_data.return_value = {
            "id": "abc123",
            "title": "Test Post",
            "selftext": "Post content here.",
            "author": "author",
            "score": 50,
            "url": "https://reddit.com/r/python/comments/abc123/",
            "num_comments": 3,
            "comments": [
                {"id": "c1", "author": "user1", "body": "Comment 1", "score": 10},
            ],
        }
        return client

    @pytest.fixture
    def service(self, mock_reddit_client):
        """Create a ContentService with mocked Reddit client."""
        return ContentService(reddit_client=mock_reddit_client)

    def test_get_content_from_url_success(self, service):
        """Test successful content extraction from URL."""
        url = "https://www.reddit.com/r/python/comments/abc123/test_post/"
        result = service.get_content_from_url(url)

        assert "post" in result
        assert "link_info" in result
        assert "user_text" in result

        assert isinstance(result["post"], RedditPost)
        assert isinstance(result["link_info"], LinkInfo)
        assert result["user_text"] is None

    def test_get_content_from_url_with_user_text(self, service):
        """Test content extraction with user text."""
        url = "https://www.reddit.com/r/python/comments/abc123/"
        user_text = "This is my opinion about the post."

        result = service.get_content_from_url(url, user_text=user_text)

        assert result["user_text"] == user_text

    def test_get_content_from_url_short_url_error(self, service):
        """Test that short URLs raise an error."""
        url = "https://redd.it/abc123"

        with pytest.raises(InvalidURLError) as exc_info:
            service.get_content_from_url(url)

        assert "Short URLs" in str(exc_info.value)

    def test_get_content_from_url_invalid_format(self, service):
        """Test that invalid URL format raises error."""
        # This URL has invalid subreddit name (too short)
        with pytest.raises(InvalidURLError):
            service.get_content_from_url("https://not-reddit.com/something")

    def test_get_content_from_url_empty_content(self, service, mock_reddit_client):
        """Test that empty content raises EmptyContentError."""
        mock_reddit_client.get_post_data.return_value = {
            "id": "abc123",
            "title": "Test Post",
            "selftext": "",  # No self text
            "author": "author",
            "score": 50,
            "url": "https://reddit.com/r/python/comments/abc123/",
            "num_comments": 0,
            "comments": [],  # No comments
        }

        url = "https://www.reddit.com/r/python/comments/abc123/"

        with pytest.raises(EmptyContentError) as exc_info:
            service.get_content_from_url(url)

        assert "no text content" in str(exc_info.value).lower()


class TestContentServicePostSummary:
    """Tests for get_post_summary method."""

    @pytest.fixture
    def service(self):
        """Create a ContentService with mocked Reddit client."""
        return ContentService(reddit_client=MagicMock())

    def test_get_post_summary(self, service):
        """Test post summary generation."""
        post = RedditPost(
            id="abc123",
            subreddit="python",
            title="A very long title that should be truncated in the summary",
            selftext="Post content",
            author="test_author",
            score=150,
            url="https://reddit.com/r/python/comments/abc123/",
            comments=[
                RedditComment(id="c1", author="user1", body="Comment 1", score=10),
                RedditComment(id="c2", author="user2", body="Comment 2", score=5),
            ],
        )

        summary = service.get_post_summary(post)

        assert summary["id"] == "abc123"
        assert summary["subreddit"] == "python"
        assert len(summary["title"]) <= 100
        assert summary["author"] == "test_author"
        assert summary["score"] == 150
        assert summary["has_selftext"] is True
        assert summary["selftext_length"] == len("Post content")
        assert summary["comments_fetched"] == 2


class TestContentServiceIntegration:
    """Integration-style tests for ContentService."""

    def test_full_workflow(self):
        """Test complete content extraction workflow."""
        mock_client = MagicMock()
        mock_client.get_post_data.return_value = {
            "id": "integ123",
            "title": "Integration Test Post",
            "selftext": "This is an integration test.",
            "author": "integration_tester",
            "score": 200,
            "url": "https://reddit.com/r/testing/comments/integ123/",
            "num_comments": 10,
            "created_utc": 1704067200.0,
            "comments": [
                {
                    "id": f"comment{i}",
                    "author": f"commenter{i}",
                    "body": f"Integration comment {i}",
                    "score": i * 10,
                    "created_utc": 1704067200.0 + i,
                }
                for i in range(5)
            ],
        }

        service = ContentService(reddit_client=mock_client)
        url = "https://www.reddit.com/r/testing/comments/integ123/integration_test/"
        user_text = "My thoughts on this post."

        # Full extraction
        result = service.get_content_from_url(url, user_text=user_text)

        # Verify result
        assert result["post"].id == "integ123"
        assert result["post"].title == "Integration Test Post"
        assert len(result["post"].comments) == 5
        assert result["link_info"].subreddit == "testing"
        assert result["link_info"].post_id == "integ123"
        assert result["user_text"] == user_text

        # Verify summary
        summary = service.get_post_summary(result["post"])
        assert summary["comments_fetched"] == 5
        assert summary["has_selftext"] is True
