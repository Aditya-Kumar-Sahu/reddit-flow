"""
Integration tests for Gemini AI client.

These tests hit the real Google Gemini API and require valid credentials.
Run with: pytest tests/integration/ -m integration -v

Environment variables required:
- GOOGLE_API_KEY
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _has_gemini_credentials() -> bool:
    """Check if Gemini credentials are available."""
    return bool(os.getenv("GOOGLE_API_KEY"))


# Skip all tests in this module if credentials not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_gemini_credentials(),
        reason="Gemini credentials not available",
    ),
]


@pytest.fixture
def gemini_client():
    """Create a real Gemini client for integration testing."""
    from reddit_flow.clients.gemini_client import GeminiClient

    config = {
        "api_key": os.getenv("GOOGLE_API_KEY"),
        "model_name": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    }
    return GeminiClient(config)


class TestGeminiIntegration:
    """Integration tests for Gemini API."""

    def test_client_initialization(self, gemini_client):
        """Test that the client initializes correctly."""
        assert gemini_client is not None
        assert gemini_client._model is not None

    @pytest.mark.slow
    def test_simple_generation(self, gemini_client):
        """Test a simple text generation."""
        response = gemini_client._model.generate_content("Say 'Hello, World!' and nothing else.")

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_extract_link_info(self, gemini_client):
        """Test extracting link info from a message."""
        message = "Check out this post: https://www.reddit.com/r/python/comments/abc123/test_post/"

        result = await gemini_client.extract_link_info(message)

        assert result is not None
        # Should return a LinkInfo object
        assert hasattr(result, "url") or hasattr(result, "subreddit")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_generate_script(self, gemini_client):
        """Test generating a video script."""
        post_text = "What are the best practices for Python testing?"
        comments_data = [
            {"body": "Use pytest for unit testing", "author": "user1", "score": 10},
            {"body": "Mock external dependencies", "author": "user2", "score": 5},
        ]

        result = await gemini_client.generate_script(
            post_text=post_text,
            comments_data=comments_data,
        )

        assert result is not None
        # Should return a VideoScript model
        assert hasattr(result, "content") or hasattr(result, "script")
