"""
Integration tests for ElevenLabs TTS client.

These tests hit the real ElevenLabs API and require valid credentials.
Run with: pytest tests/integration/ -m integration -v

Environment variables required:
- ELEVENLABS_API_KEY
- ELEVENLABS_VOICE_ID (optional, uses default if not set)
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _has_elevenlabs_credentials() -> bool:
    """Check if ElevenLabs credentials are available."""
    return bool(os.getenv("ELEVENLABS_API_KEY"))


# Skip all tests in this module if credentials not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_elevenlabs_credentials(),
        reason="ElevenLabs credentials not available",
    ),
]


@pytest.fixture
def elevenlabs_client():
    """Create a real ElevenLabs client for integration testing."""
    from reddit_flow.clients.elevenlabs_client import ElevenLabsClient

    config = {
        "api_key": os.getenv("ELEVENLABS_API_KEY"),
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID"),
    }
    return ElevenLabsClient(config)


class TestElevenLabsIntegration:
    """Integration tests for ElevenLabs API."""

    def test_client_initialization(self, elevenlabs_client):
        """Test that the client initializes correctly."""
        assert elevenlabs_client is not None

    def test_verify_service(self, elevenlabs_client):
        """Test API connection verification."""
        # Should not raise an exception
        result = elevenlabs_client.verify_service()
        assert result is True

    def test_get_user_info(self, elevenlabs_client):
        """Test fetching user information."""
        import requests

        api_key = os.getenv("ELEVENLABS_API_KEY")
        url = "https://api.elevenlabs.io/v1/user"
        headers = {"xi-api-key": api_key}

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        assert "subscription" in data

    @pytest.mark.slow
    @pytest.mark.costly
    def test_text_to_speech(self, elevenlabs_client):
        """Test generating audio from text.

        Note: This test consumes character quota.
        Mark as 'costly' to skip in regular runs.
        """
        # text_to_speech returns bytes, not a file
        result = elevenlabs_client.text_to_speech(
            text="Hello, this is a test.",
        )

        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0
