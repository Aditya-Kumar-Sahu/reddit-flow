"""
Pytest configuration and shared fixtures for reddit-flow tests.

This module provides:
- Common fixtures for mocking external APIs
- Test data factories
- Configuration helpers
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Environment Configuration
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def load_test_environment():
    """Load test environment variables before running tests."""
    from dotenv import load_dotenv
    load_dotenv()
    yield


@pytest.fixture
def mock_env_vars(monkeypatch) -> Dict[str, str]:
    """
    Provide mock environment variables for testing.
    
    Usage:
        def test_something(mock_env_vars):
            # Environment is already configured with test values
            pass
    """
    test_vars = {
        "TELEGRAM_BOT_TOKEN": "test_telegram_token",
        "REDDIT_CLIENT_ID": "test_reddit_client_id",
        "REDDIT_CLIENT_SECRET": "test_reddit_client_secret",
        "REDDIT_USER_AGENT": "test_user_agent",
        "REDDIT_USERNAME": "test_username",
        "REDDIT_PASSWORD": "test_password",
        "GOOGLE_API_KEY": "test_google_api_key",
        "ELEVENLABS_API_KEY": "test_elevenlabs_key",
        "ELEVENLABS_VOICE_ID": "test_voice_id",
        "HEYGEN_API_KEY": "test_heygen_key",
        "HEYGEN_AVATAR_ID": "test_avatar_id",
        "YOUTUBE_CLIENT_SECRETS_FILE": "test_secrets.json",
    }
    
    for key, value in test_vars.items():
        monkeypatch.setenv(key, value)
    
    return test_vars


# =============================================================================
# Mock Fixtures for External APIs
# =============================================================================

@pytest.fixture
def mock_praw():
    """
    Mock PRAW Reddit client.
    
    Usage:
        def test_reddit(mock_praw):
            mock_praw.submission.return_value = create_mock_submission()
    """
    with patch("praw.Reddit") as mock_reddit:
        mock_instance = MagicMock()
        mock_reddit.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_genai():
    """
    Mock Google Generative AI client.
    
    Usage:
        def test_gemini(mock_genai):
            mock_genai.GenerativeModel.return_value.generate_content_async = AsyncMock(...)
    """
    with patch("google.generativeai") as mock:
        yield mock


@pytest.fixture
def mock_requests():
    """
    Mock requests library for HTTP calls.
    
    Usage:
        def test_api_call(mock_requests):
            mock_requests.post.return_value.json.return_value = {"status": "ok"}
    """
    with patch("requests.post") as mock_post, \
         patch("requests.get") as mock_get, \
         patch("requests.head") as mock_head:
        mock = MagicMock()
        mock.post = mock_post
        mock.get = mock_get
        mock.head = mock_head
        yield mock


@pytest.fixture
def mock_telegram_update():
    """Create a mock Telegram Update object."""
    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.text = "https://reddit.com/r/test/comments/abc123/"
    return update


@pytest.fixture
def mock_telegram_context():
    """Create a mock Telegram Context object."""
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


# =============================================================================
# Test Data Factories
# =============================================================================

@pytest.fixture
def sample_reddit_post() -> Dict[str, Any]:
    """Provide sample Reddit post data for testing."""
    return {
        "title": "Test Post Title",
        "selftext": "This is the body of the test post with some content.",
        "url": "https://reddit.com/r/test/comments/abc123/",
        "author": "test_user",
        "score": 100,
        "comments": [
            {
                "id": "comment1",
                "body": "This is a top comment",
                "author": "commenter1",
                "depth": 0,
                "score": 50
            },
            {
                "id": "comment2",
                "body": "This is a reply",
                "author": "commenter2",
                "depth": 1,
                "score": 25
            }
        ]
    }


@pytest.fixture
def sample_script_data() -> Dict[str, str]:
    """Provide sample generated script data for testing."""
    return {
        "script": "This is a test script for the video. It discusses the Reddit post content.",
        "title": "Amazing Discussion About Test Topic"
    }


@pytest.fixture
def sample_link_info() -> Dict[str, str | None]:
    """Provide sample extracted link information for testing."""
    return {
        "link": "https://reddit.com/r/test/comments/abc123/",
        "subReddit": "test",
        "postId": "abc123",
        "text": None
    }


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def temp_directory(tmp_path) -> Path:
    """
    Provide a temporary directory for test files.
    
    This directory is automatically cleaned up after each test.
    """
    return tmp_path


@pytest.fixture
def mock_video_file(tmp_path) -> Path:
    """Create a mock video file for upload tests."""
    video_path = tmp_path / "test_video.mp4"
    video_path.write_bytes(b"fake video content" * 1000)
    return video_path


@pytest.fixture
def mock_audio_bytes() -> bytes:
    """Provide mock audio data for TTS tests."""
    return b"fake audio content" * 100


# =============================================================================
# Async Helpers
# =============================================================================

@pytest.fixture
def event_loop_policy():
    """Configure event loop for async tests."""
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.get_event_loop_policy()


# =============================================================================
# Skip Conditions
# =============================================================================

def has_reddit_credentials() -> bool:
    """Check if Reddit credentials are configured."""
    return all([
        os.getenv("REDDIT_CLIENT_ID"),
        os.getenv("REDDIT_CLIENT_SECRET"),
        os.getenv("REDDIT_USERNAME"),
        os.getenv("REDDIT_PASSWORD"),
    ])


def has_google_credentials() -> bool:
    """Check if Google API key is configured."""
    return bool(os.getenv("GOOGLE_API_KEY"))


def has_elevenlabs_credentials() -> bool:
    """Check if ElevenLabs API key is configured."""
    return bool(os.getenv("ELEVENLABS_API_KEY"))


def has_heygen_credentials() -> bool:
    """Check if HeyGen API key is configured."""
    return bool(os.getenv("HEYGEN_API_KEY"))


def has_youtube_credentials() -> bool:
    """Check if YouTube credentials are configured."""
    secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE")
    return bool(secrets_file and Path(secrets_file).exists())


# Skip markers for integration tests
skip_without_reddit = pytest.mark.skipif(
    not has_reddit_credentials(),
    reason="Reddit credentials not configured"
)

skip_without_google = pytest.mark.skipif(
    not has_google_credentials(),
    reason="Google API key not configured"
)

skip_without_elevenlabs = pytest.mark.skipif(
    not has_elevenlabs_credentials(),
    reason="ElevenLabs API key not configured"
)

skip_without_heygen = pytest.mark.skipif(
    not has_heygen_credentials(),
    reason="HeyGen API key not configured"
)

skip_without_youtube = pytest.mark.skipif(
    not has_youtube_credentials(),
    reason="YouTube credentials not configured"
)
