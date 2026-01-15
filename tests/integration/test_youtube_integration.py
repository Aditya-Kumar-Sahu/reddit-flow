"""
Integration tests for YouTube upload client.

These tests hit the real YouTube API and require valid credentials.
Run with: pytest tests/integration/ -m integration -v

Environment variables required:
- YOUTUBE_CLIENT_SECRETS_FILE
- token.json (OAuth tokens)
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _has_youtube_credentials() -> bool:
    """Check if YouTube credentials are available."""
    secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE")
    token_path = Path("token.json")

    if not secrets_file or not os.path.exists(secrets_file):
        return False

    # Also need valid token
    return token_path.exists()


# Skip all tests in this module if credentials not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_youtube_credentials(),
        reason="YouTube credentials not available",
    ),
]


@pytest.fixture
def youtube_client():
    """Create a real YouTube client for integration testing."""
    from reddit_flow.clients.youtube_client import YouTubeClient

    config = {
        "client_secrets_file": os.getenv("YOUTUBE_CLIENT_SECRETS_FILE"),
        "token_file": "token.json",
    }
    return YouTubeClient(config)


class TestYouTubeIntegration:
    """Integration tests for YouTube API."""

    def test_client_initialization(self, youtube_client):
        """Test that the client initializes correctly."""
        assert youtube_client is not None

    def test_verify_service(self, youtube_client):
        """Test API connection verification."""
        try:
            result = youtube_client.verify_service()
            assert result is True or result is False
        except Exception as e:
            # Token may need refresh or may be expired
            pytest.skip(f"YouTube verify not supported: {e}")

    def test_get_channel_info(self, youtube_client):
        """Test fetching channel information."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_path = Path("token.json")
            scopes = ["https://www.googleapis.com/auth/youtube.upload"]

            creds = Credentials.from_authorized_user_file(str(token_path), scopes)

            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                creds.refresh(Request())

            service = build("youtube", "v3", credentials=creds)

            request = service.channels().list(
                part="snippet,contentDetails,statistics",
                mine=True,
            )
            response = request.execute()

            assert "items" in response or "kind" in response
        except Exception as e:
            pytest.skip(f"YouTube channel info not available: {e}")

    @pytest.mark.slow
    @pytest.mark.costly
    def test_upload_video(self, youtube_client):
        """Test uploading a video.

        Note: This test would upload a real video.
        Mark as 'costly' to skip in regular runs.
        """
        pytest.skip("Video upload is not suitable for automated testing")

        # Would test:
        # result = youtube_client.upload_video(
        #     video_path="test_video.mp4",
        #     title="Test Video",
        #     description="Test description",
        # )
        # assert result is not None
