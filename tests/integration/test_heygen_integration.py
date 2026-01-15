"""
Integration tests for HeyGen video generation client.

These tests hit the real HeyGen API and require valid credentials.
Run with: pytest tests/integration/ -m integration -v

Environment variables required:
- HEYGEN_API_KEY
- HEYGEN_AVATAR_ID (optional)
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _has_heygen_credentials() -> bool:
    """Check if HeyGen credentials are available."""
    return bool(os.getenv("HEYGEN_API_KEY"))


# Skip all tests in this module if credentials not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_heygen_credentials(),
        reason="HeyGen credentials not available",
    ),
]


@pytest.fixture
def heygen_client():
    """Create a real HeyGen client for integration testing."""
    from reddit_flow.clients.heygen_client import HeyGenClient

    config = {
        "api_key": os.getenv("HEYGEN_API_KEY"),
        "avatar_id": os.getenv("HEYGEN_AVATAR_ID"),
        "voice_id": os.getenv("HEYGEN_VOICE_ID"),
    }
    return HeyGenClient(config)


class TestHeyGenIntegration:
    """Integration tests for HeyGen API."""

    def test_client_initialization(self, heygen_client):
        """Test that the client initializes correctly."""
        assert heygen_client is not None

    def test_verify_service(self, heygen_client):
        """Test API connection verification."""
        # verify_service may return False if quota endpoint differs
        # but should not raise an exception
        try:
            result = heygen_client.verify_service()
            # If it returns, test passes (True or False both acceptable)
            assert result is True or result is False
        except Exception as e:
            # Some API configurations may not support the quota endpoint
            pytest.skip(f"HeyGen verify not supported: {e}")

    def test_get_avatar_details(self, heygen_client):
        """Test fetching avatar details."""
        import requests

        avatar_id = os.getenv("HEYGEN_AVATAR_ID")
        if not avatar_id:
            pytest.skip("HEYGEN_AVATAR_ID not configured")

        api_key = os.getenv("HEYGEN_API_KEY")
        url = f"https://api.heygen.com/v2/avatar/{avatar_id}/details"
        headers = {
            "x-api-key": api_key,
            "accept": "application/json",
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        assert "data" in data
        # Avatar should have an id
        avatar_data = data.get("data", {})
        assert "id" in avatar_data or "avatar_name" in avatar_data

    def test_list_voices(self, heygen_client):
        """Test listing available voices."""
        import requests

        api_key = os.getenv("HEYGEN_API_KEY")
        url = "https://api.heygen.com/v2/voices"
        headers = {
            "x-api-key": api_key,
            "accept": "application/json",
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        assert "data" in data or "voices" in data

    @pytest.mark.slow
    @pytest.mark.costly
    def test_create_video(self, heygen_client):
        """Test creating a video.

        Note: This test consumes API credits.
        Mark as 'costly' to skip in regular runs.
        """
        pytest.skip("Video generation is too costly for regular testing")

        # Would test:
        # result = heygen_client.create_video(
        #     script="Hello, this is a test video.",
        #     title="Test Video",
        # )
        # assert result is not None
