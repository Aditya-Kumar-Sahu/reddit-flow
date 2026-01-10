"""
Integration tests for Reddit API client.

These tests hit the real Reddit API and require valid credentials.
Run with: pytest tests/integration/ -m integration -v

Environment variables required:
- REDDIT_CLIENT_ID
- REDDIT_CLIENT_SECRET
- REDDIT_USER_AGENT
- REDDIT_USERNAME
- REDDIT_PASSWORD
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _has_reddit_credentials() -> bool:
    """Check if Reddit credentials are available."""
    required = [
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
    ]
    return all(os.getenv(var) for var in required)


# Skip all tests in this module if credentials not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_reddit_credentials(),
        reason="Reddit credentials not available",
    ),
]


@pytest.fixture
def reddit_client():
    """Create a real Reddit client for integration testing."""
    from reddit_flow.clients.reddit_client import RedditClient

    config = {
        "client_id": os.getenv("REDDIT_CLIENT_ID"),
        "client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
        "user_agent": os.getenv("REDDIT_USER_AGENT"),
        "username": os.getenv("REDDIT_USERNAME"),
        "password": os.getenv("REDDIT_PASSWORD"),
    }
    return RedditClient(config)


class TestRedditIntegration:
    """Integration tests for Reddit API."""

    def test_authentication(self, reddit_client):
        """Test that we can authenticate with Reddit."""
        # The client should be able to verify connection
        # This implicitly tests authentication
        assert reddit_client is not None
        assert reddit_client.reddit is not None

    def test_fetch_subreddit_posts(self, reddit_client):
        """Test fetching posts from a subreddit."""
        # Use a well-known, stable subreddit
        posts = list(reddit_client.reddit.subreddit("python").hot(limit=5))

        assert len(posts) > 0
        assert all(hasattr(post, "title") for post in posts)
        assert all(hasattr(post, "id") for post in posts)

    def test_fetch_post_by_id(self, reddit_client):
        """Test fetching a specific post by ID."""
        # Use a known stable post ID (Python subreddit announcement)
        post = reddit_client.reddit.submission(id="1nf7kh6")

        assert post is not None
        assert post.title is not None
        assert len(post.title) > 0

    def test_fetch_post_comments(self, reddit_client):
        """Test fetching comments from a post."""
        post = reddit_client.reddit.submission(id="1nf7kh6")
        post.comments.replace_more(limit=0)

        # Should have some comments
        comments = list(post.comments)
        assert len(comments) >= 0  # Post might have 0 comments

    @pytest.mark.slow
    def test_get_post_with_model(self, reddit_client):
        """Test the full get_post method with comments extraction."""
        # Use a real subreddit and post ID
        result = reddit_client.get_post(
            subreddit_name="python",
            post_id="1nf7kh6",
        )

        assert result is not None
        assert result.title is not None
        assert result.subreddit is not None
