"""
Unit tests for the Reddit API client.

Tests for src/reddit_flow/clients/reddit_client.py
"""

from unittest.mock import MagicMock, patch

import pytest

from reddit_flow.clients import RedditClient
from reddit_flow.exceptions import ConfigurationError, RedditAPIError
from reddit_flow.models import RedditComment, RedditPost

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_reddit_credentials():
    """Mock environment variables for Reddit credentials."""
    return {
        "REDDIT_CLIENT_ID": "test_client_id",
        "REDDIT_CLIENT_SECRET": "test_client_secret",
        "REDDIT_USER_AGENT": "test_user_agent",
        "REDDIT_USERNAME": "test_username",
        "REDDIT_PASSWORD": "test_password",
    }


@pytest.fixture
def mock_praw_reddit():
    """Create a mock PRAW Reddit instance."""
    with patch("reddit_flow.clients.reddit_client.praw.Reddit") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def reddit_config():
    """Configuration dictionary for Reddit client."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "user_agent": "test_user_agent",
        "username": "test_username",
        "password": "test_password",
    }


@pytest.fixture
def mock_submission():
    """Create a mock Reddit submission."""
    submission = MagicMock()
    submission.title = "Test Post Title"
    submission.selftext = "This is the post body"
    submission.url = "https://reddit.com/r/test/comments/abc123/"
    submission.author = MagicMock()
    submission.author.__str__ = lambda x: "test_author"
    submission.score = 100

    # Mock comments
    mock_comment = MagicMock()
    mock_comment.id = "comment1"
    mock_comment.body = "This is a comment"
    mock_comment.author = MagicMock()
    mock_comment.author.__str__ = lambda x: "commenter1"
    mock_comment.score = 50
    mock_comment.replies = MagicMock()
    mock_comment.replies.list.return_value = []

    submission.comments = MagicMock()
    submission.comments.replace_more = MagicMock()
    submission.comments.list.return_value = [mock_comment]

    return submission


# =============================================================================
# Initialization Tests
# =============================================================================


class TestRedditClientInitialization:
    """Tests for RedditClient initialization."""

    def test_init_with_config(self, mock_praw_reddit, reddit_config):
        """Test initialization with config dictionary."""
        client = RedditClient(config=reddit_config)

        assert client.is_initialized
        assert client.service_name == "Reddit"
        assert client.reddit is not None

    def test_init_with_env_vars(self, mock_praw_reddit, mock_reddit_credentials):
        """Test initialization with environment variables."""
        with patch.dict("os.environ", mock_reddit_credentials):
            client = RedditClient()
            assert client.is_initialized

    def test_init_missing_credentials_raises_error(self, mock_praw_reddit):
        """Test that missing credentials raise ConfigurationError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                RedditClient(config={})

            assert "Missing Reddit credentials" in str(exc_info.value)
            assert "missing" in exc_info.value.details

    def test_init_partial_credentials_raises_error(self, mock_praw_reddit):
        """Test that partial credentials raise ConfigurationError."""
        with patch.dict("os.environ", {"REDDIT_CLIENT_ID": "only_id"}, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                RedditClient(config={})

            missing = exc_info.value.details["missing"]
            assert "client_secret/REDDIT_CLIENT_SECRET" in missing
            assert "user_agent/REDDIT_USER_AGENT" in missing

    def test_init_with_custom_limits(self, mock_praw_reddit, reddit_config):
        """Test initialization with custom comment limits."""
        client = RedditClient(
            config=reddit_config,
            max_comments=100,
            max_comment_depth=10,
        )

        assert client.max_comments == 100
        assert client.max_comment_depth == 10

    def test_init_praw_exception_raises_reddit_api_error(self):
        """Test that PRAW exceptions during init raise RedditAPIError."""
        with patch("reddit_flow.clients.reddit_client.praw.Reddit") as mock:
            mock.side_effect = Exception("PRAW initialization failed")

            with pytest.raises(RedditAPIError) as exc_info:
                RedditClient(
                    config={
                        "client_id": "id",
                        "client_secret": "secret",
                        "user_agent": "agent",
                    }
                )

            assert "initialization failed" in str(exc_info.value)


# =============================================================================
# Health Check Tests
# =============================================================================


class TestRedditClientHealthCheck:
    """Tests for RedditClient health check."""

    def test_health_check_success(self, mock_praw_reddit, reddit_config):
        """Test successful health check."""
        mock_subreddit = MagicMock()
        mock_subreddit.id = "test_id"
        mock_praw_reddit.subreddit.return_value = mock_subreddit

        client = RedditClient(config=reddit_config)
        result = client.verify_service()

        assert result is True
        mock_praw_reddit.subreddit.assert_called_with("test")

    def test_health_check_failure(self, mock_praw_reddit, reddit_config):
        """Test health check failure raises error."""
        mock_praw_reddit.subreddit.side_effect = Exception("API error")

        client = RedditClient(config=reddit_config)

        with pytest.raises(RedditAPIError) as exc_info:
            client.verify_service()

        assert "health check failed" in str(exc_info.value)


# =============================================================================
# Get Post Tests
# =============================================================================


class TestRedditClientGetPost:
    """Tests for RedditClient.get_post method."""

    def test_get_post_returns_reddit_post_model(
        self, mock_praw_reddit, reddit_config, mock_submission
    ):
        """Test that get_post returns a RedditPost model."""
        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        post = client.get_post("test", "abc123")

        assert isinstance(post, RedditPost)
        assert post.id == "abc123"
        assert post.subreddit == "test"
        assert post.title == "Test Post Title"
        assert post.selftext == "This is the post body"

    def test_get_post_extracts_comments(self, mock_praw_reddit, reddit_config, mock_submission):
        """Test that get_post extracts comments correctly."""
        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        post = client.get_post("test", "abc123")

        assert len(post.comments) == 1
        assert isinstance(post.comments[0], RedditComment)
        assert post.comments[0].id == "comment1"
        assert post.comments[0].body == "This is a comment"

    def test_get_post_handles_deleted_author(
        self, mock_praw_reddit, reddit_config, mock_submission
    ):
        """Test handling of deleted post author."""
        mock_submission.author = None
        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        post = client.get_post("test", "abc123")

        assert post.author == "[deleted]"

    def test_get_post_invalid_url_raises_error(self, mock_praw_reddit, reddit_config):
        """Test that invalid URLs raise RedditAPIError."""
        import praw.exceptions

        mock_praw_reddit.submission.side_effect = praw.exceptions.InvalidURL("Invalid URL")

        client = RedditClient(config=reddit_config)

        with pytest.raises(RedditAPIError) as exc_info:
            client.get_post("test", "invalid")

        assert "Invalid" in str(exc_info.value)
        assert exc_info.value.details["post_id"] == "invalid"

    def test_get_post_api_exception_raises_error(self, mock_praw_reddit, reddit_config):
        """Test that API exceptions raise RedditAPIError."""
        import praw.exceptions

        mock_praw_reddit.submission.side_effect = praw.exceptions.PRAWException(
            "API error occurred"
        )

        client = RedditClient(config=reddit_config)

        with pytest.raises(RedditAPIError) as exc_info:
            client.get_post("test", "problematic")

        assert "problematic" in str(exc_info.value.details)


# =============================================================================
# Get Post Data Tests (Backward Compatibility)
# =============================================================================


class TestRedditClientGetPostData:
    """Tests for RedditClient.get_post_data backward compatibility method."""

    def test_get_post_data_returns_dict(self, mock_praw_reddit, reddit_config, mock_submission):
        """Test that get_post_data returns a dictionary."""
        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        data = client.get_post_data("test", "abc123")

        assert isinstance(data, dict)
        assert data["title"] == "Test Post Title"
        assert data["selftext"] == "This is the post body"
        assert "comments" in data
        assert isinstance(data["comments"], list)

    def test_get_post_data_comment_format(self, mock_praw_reddit, reddit_config, mock_submission):
        """Test that comments are formatted correctly in dict output."""
        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        data = client.get_post_data("test", "abc123")

        comment = data["comments"][0]
        assert "id" in comment
        assert "body" in comment
        assert "author" in comment
        assert "depth" in comment
        assert "score" in comment


# =============================================================================
# Comment Extraction Tests
# =============================================================================


class TestRedditClientCommentExtraction:
    """Tests for comment extraction functionality."""

    def test_extract_comments_respects_depth_limit(self, mock_praw_reddit, reddit_config):
        """Test that comment extraction respects max depth."""

        # Create nested comments
        def create_nested_comment(depth, max_depth=10):
            comment = MagicMock()
            comment.id = f"comment_depth_{depth}"
            comment.body = f"Comment at depth {depth}"
            comment.author = MagicMock()
            comment.author.__str__ = lambda x: f"author_{depth}"
            comment.score = 10

            if depth < max_depth:
                reply = create_nested_comment(depth + 1, max_depth)
                comment.replies = MagicMock()
                comment.replies.list.return_value = [reply]
                comment.replies.__len__ = lambda x: 1
            else:
                comment.replies = MagicMock()
                comment.replies.list.return_value = []
                comment.replies.__len__ = lambda x: 0

            return comment

        root_comment = create_nested_comment(0, 10)

        mock_submission = MagicMock()
        mock_submission.title = "Test"
        mock_submission.selftext = ""
        mock_submission.url = "https://reddit.com/"
        mock_submission.author = None
        mock_submission.score = 0
        mock_submission.comments = MagicMock()
        mock_submission.comments.replace_more = MagicMock()
        mock_submission.comments.list.return_value = [root_comment]

        mock_praw_reddit.submission.return_value = mock_submission

        # Client with max_depth=3
        client = RedditClient(config=reddit_config, max_comment_depth=3)
        post = client.get_post("test", "abc")

        # Should have comments at depths 0, 1, 2, 3 but not beyond
        depths = [c.depth for c in post.comments]
        assert max(depths) <= 3

    def test_extract_comments_skips_more_comments(self, mock_praw_reddit, reddit_config):
        """Test that MoreComments objects are skipped."""
        import praw.models

        mock_more = MagicMock(spec=praw.models.MoreComments)

        regular_comment = MagicMock()
        regular_comment.id = "real_comment"
        regular_comment.body = "Real comment"
        regular_comment.author = MagicMock()
        regular_comment.author.__str__ = lambda x: "author"
        regular_comment.score = 10
        regular_comment.replies = MagicMock()
        regular_comment.replies.list.return_value = []

        mock_submission = MagicMock()
        mock_submission.title = "Test"
        mock_submission.selftext = ""
        mock_submission.url = "https://reddit.com/"
        mock_submission.author = None
        mock_submission.score = 0
        mock_submission.comments = MagicMock()
        mock_submission.comments.replace_more = MagicMock()
        mock_submission.comments.list.return_value = [mock_more, regular_comment]

        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        post = client.get_post("test", "abc")

        # Should only have the real comment, not the MoreComments
        assert len(post.comments) == 1
        assert post.comments[0].id == "real_comment"

    def test_extract_comments_handles_errors_gracefully(self, mock_praw_reddit, reddit_config):
        """Test that comment extraction errors are logged but don't crash."""
        bad_comment = MagicMock()
        bad_comment.id = "bad_comment"
        # Make body access raise an exception
        type(bad_comment).body = property(lambda x: (_ for _ in ()).throw(Exception("Body error")))

        good_comment = MagicMock()
        good_comment.id = "good_comment"
        good_comment.body = "Good comment"
        good_comment.author = MagicMock()
        good_comment.author.__str__ = lambda x: "author"
        good_comment.score = 10
        good_comment.replies = MagicMock()
        good_comment.replies.list.return_value = []

        mock_submission = MagicMock()
        mock_submission.title = "Test"
        mock_submission.selftext = ""
        mock_submission.url = "https://reddit.com/"
        mock_submission.author = None
        mock_submission.score = 0
        mock_submission.comments = MagicMock()
        mock_submission.comments.replace_more = MagicMock()
        mock_submission.comments.list.return_value = [bad_comment, good_comment]

        mock_praw_reddit.submission.return_value = mock_submission

        client = RedditClient(config=reddit_config)
        post = client.get_post("test", "abc")

        # Should have the good comment despite the bad one failing
        assert len(post.comments) == 1
        assert post.comments[0].id == "good_comment"


# =============================================================================
# Integration-Style Tests (Still Mocked)
# =============================================================================


class TestRedditClientIntegration:
    """Integration-style tests for complete workflows."""

    def test_full_post_fetch_workflow(self, mock_praw_reddit, reddit_config):
        """Test a complete post fetch workflow."""
        # Create a realistic mock submission with nested comments
        reply = MagicMock()
        reply.id = "reply1"
        reply.body = "This is a reply"
        reply.author = MagicMock()
        reply.author.__str__ = lambda x: "replier"
        reply.score = 25
        reply.replies = MagicMock()
        reply.replies.list.return_value = []
        reply.replies.__len__ = lambda x: 0

        comment = MagicMock()
        comment.id = "comment1"
        comment.body = "This is a top comment"
        comment.author = MagicMock()
        comment.author.__str__ = lambda x: "commenter"
        comment.score = 100
        comment.replies = MagicMock()
        comment.replies.list.return_value = [reply]
        comment.replies.__len__ = lambda x: 1

        submission = MagicMock()
        submission.title = "Amazing Discovery"
        submission.selftext = "Scientists have discovered something incredible!"
        submission.url = "https://reddit.com/r/science/comments/xyz789/"
        submission.author = MagicMock()
        submission.author.__str__ = lambda x: "scientist_user"
        submission.score = 5000
        submission.comments = MagicMock()
        submission.comments.replace_more = MagicMock()
        submission.comments.list.return_value = [comment]

        mock_praw_reddit.submission.return_value = submission

        # Execute
        client = RedditClient(config=reddit_config)
        post = client.get_post("science", "xyz789")

        # Verify
        assert post.title == "Amazing Discovery"
        assert post.score == 5000
        assert len(post.comments) == 2  # Top comment + reply
        assert post.comments[0].body == "This is a top comment"
        assert post.comments[1].body == "This is a reply"
        assert post.comments[1].depth == 1
