"""
Unit tests for ElevenLabsClient.

Tests the ElevenLabs TTS client with comprehensive mocking
of the requests library.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from reddit_flow.clients.elevenlabs_client import ElevenLabsClient
from reddit_flow.exceptions import ConfigurationError, TTSError

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def elevenlabs_config():
    """Valid ElevenLabs client configuration."""
    return {
        "api_key": "test-api-key",
        "voice_id": "test-voice-id",
    }


@pytest.fixture
def elevenlabs_client(elevenlabs_config):
    """Create an ElevenLabsClient with valid config."""
    return ElevenLabsClient(config=elevenlabs_config)


@pytest.fixture
def mock_response():
    """Create a mock requests response."""
    response = MagicMock()
    response.status_code = 200
    response.content = b"fake audio content bytes"
    response.text = '{"status": "ok"}'
    response.json.return_value = {"status": "ok"}
    return response


# =============================================================================
# Initialization Tests
# =============================================================================


class TestElevenLabsClientInitialization:
    """Tests for ElevenLabsClient initialization."""

    def test_init_with_config(self, elevenlabs_config):
        """Test initialization with explicit config."""
        client = ElevenLabsClient(config=elevenlabs_config)

        assert client.is_initialized
        assert client.service_name == "ElevenLabs"
        assert client.voice_id == "test-voice-id"
        assert client.base_url == ElevenLabsClient.DEFAULT_BASE_URL

    def test_init_with_env_vars(self, monkeypatch):
        """Test initialization using environment variables."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "env-api-key")
        monkeypatch.setenv("ELEVENLABS_VOICE_ID", "env-voice-id")

        client = ElevenLabsClient()

        assert client.is_initialized
        assert client.voice_id == "env-voice-id"

    def test_init_missing_api_key_raises_error(self, monkeypatch):
        """Test that missing API key raises ConfigurationError."""
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            ElevenLabsClient(config={"voice_id": "test"})

        assert "API key not found" in str(exc_info.value)

    def test_init_missing_voice_id_raises_error(self, monkeypatch):
        """Test that missing voice ID raises ConfigurationError."""
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            ElevenLabsClient(config={"api_key": "test"})

        assert "voice ID not found" in str(exc_info.value)

    def test_init_with_custom_base_url(self):
        """Test initialization with custom base URL."""
        config = {
            "api_key": "test-key",
            "voice_id": "test-voice",
            "base_url": "https://custom.elevenlabs.io/v1",
        }

        client = ElevenLabsClient(config=config)

        assert client.base_url == "https://custom.elevenlabs.io/v1"

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        config = {
            "api_key": "test-key",
            "voice_id": "test-voice",
            "timeout": 120,
        }

        client = ElevenLabsClient(config=config)

        assert client._timeout == 120


# =============================================================================
# Health Check Tests
# =============================================================================


class TestElevenLabsClientHealthCheck:
    """Tests for ElevenLabsClient health check."""

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_health_check_success(self, mock_get, elevenlabs_client, mock_response):
        """Test successful health check."""
        mock_get.return_value = mock_response

        result = elevenlabs_client._health_check()

        assert result is True
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "/user/subscription" in call_url

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_health_check_failure_status(self, mock_get, elevenlabs_client):
        """Test health check with non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = elevenlabs_client._health_check()

        assert result is False

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_health_check_exception(self, mock_get, elevenlabs_client):
        """Test health check with network exception."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = elevenlabs_client._health_check()

        assert result is False


# =============================================================================
# Text to Speech Tests
# =============================================================================


class TestElevenLabsClientTextToSpeech:
    """Tests for text_to_speech method."""

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_success(self, mock_post, elevenlabs_client):
        """Test successful text-to-speech conversion."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio bytes here"
        mock_post.return_value = mock_response

        result = elevenlabs_client.text_to_speech("Hello, world!")

        assert result == b"audio bytes here"
        mock_post.assert_called_once()

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_builds_correct_url(self, mock_post, elevenlabs_client):
        """Test that correct URL is built with voice ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"
        mock_post.return_value = mock_response

        elevenlabs_client.text_to_speech("Test")

        call_url = mock_post.call_args[0][0]
        assert f"/text-to-speech/{elevenlabs_client.voice_id}" in call_url

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_sends_correct_headers(self, mock_post, elevenlabs_client):
        """Test that correct headers are sent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"
        mock_post.return_value = mock_response

        elevenlabs_client.text_to_speech("Test")

        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs["headers"]
        assert "xi-api-key" in headers
        assert headers["xi-api-key"] == "test-api-key"
        assert headers["Content-Type"] == "application/json"

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_sends_text_payload(self, mock_post, elevenlabs_client):
        """Test that text is sent in request payload."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"
        mock_post.return_value = mock_response

        elevenlabs_client.text_to_speech("Hello, world!")

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"] == {"text": "Hello, world!"}

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_http_error_raises_tts_error(self, mock_post, elevenlabs_client):
        """Test that HTTP errors are wrapped in TTSError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with pytest.raises(TTSError) as exc_info:
            elevenlabs_client.text_to_speech("Test")

        assert "conversion failed" in str(exc_info.value)

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_network_error_raises_tts_error(self, mock_post, elevenlabs_client):
        """Test that network errors are wrapped in TTSError."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        with pytest.raises(TTSError) as exc_info:
            elevenlabs_client.text_to_speech("Test")

        assert "Network error" in str(exc_info.value)

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    def test_text_to_speech_generic_error_raises_tts_error(self, mock_post, elevenlabs_client):
        """Test that generic errors are wrapped in TTSError."""
        mock_post.side_effect = ValueError("Unexpected error")

        with pytest.raises(TTSError) as exc_info:
            elevenlabs_client.text_to_speech("Test")

        assert "Failed to convert" in str(exc_info.value)


# =============================================================================
# Get Voices Tests
# =============================================================================


class TestElevenLabsClientGetVoices:
    """Tests for get_voices method."""

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_get_voices_success(self, mock_get, elevenlabs_client):
        """Test successful voice list retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "voices": [
                {"voice_id": "voice1", "name": "Alice"},
                {"voice_id": "voice2", "name": "Bob"},
            ]
        }
        mock_get.return_value = mock_response

        result = elevenlabs_client.get_voices()

        assert len(result) == 2
        assert result[0]["name"] == "Alice"

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_get_voices_empty_list(self, mock_get, elevenlabs_client):
        """Test handling of empty voice list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"voices": []}
        mock_get.return_value = mock_response

        result = elevenlabs_client.get_voices()

        assert result == []

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_get_voices_error_raises_tts_error(self, mock_get, elevenlabs_client):
        """Test that API errors are wrapped in TTSError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with pytest.raises(TTSError) as exc_info:
            elevenlabs_client.get_voices()

        assert "Failed to get voices" in str(exc_info.value)


# =============================================================================
# Get User Info Tests
# =============================================================================


class TestElevenLabsClientGetUserInfo:
    """Tests for get_user_info method."""

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_get_user_info_success(self, mock_get, elevenlabs_client):
        """Test successful user info retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tier": "pro",
            "character_count": 5000,
            "character_limit": 100000,
        }
        mock_get.return_value = mock_response

        result = elevenlabs_client.get_user_info()

        assert result["tier"] == "pro"
        assert result["character_count"] == 5000

    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_get_user_info_error_raises_tts_error(self, mock_get, elevenlabs_client):
        """Test that API errors are wrapped in TTSError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with pytest.raises(TTSError) as exc_info:
            elevenlabs_client.get_user_info()

        assert "Failed to get user info" in str(exc_info.value)


# =============================================================================
# Auth Headers Tests
# =============================================================================


class TestElevenLabsClientAuthHeaders:
    """Tests for _get_auth_headers method."""

    def test_get_auth_headers_includes_api_key(self, elevenlabs_client):
        """Test that headers include API key."""
        headers = elevenlabs_client._get_auth_headers()

        assert "xi-api-key" in headers
        assert headers["xi-api-key"] == "test-api-key"

    def test_get_auth_headers_includes_content_type(self, elevenlabs_client):
        """Test that headers include content type."""
        headers = elevenlabs_client._get_auth_headers()

        assert headers["Content-Type"] == "application/json"

    def test_get_auth_headers_merges_extra(self, elevenlabs_client):
        """Test that extra headers are merged."""
        headers = elevenlabs_client._get_auth_headers(extra={"X-Custom": "value"})

        assert headers["X-Custom"] == "value"
        assert "xi-api-key" in headers


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestElevenLabsClientIntegration:
    """Integration-style tests for the full workflow."""

    @patch("reddit_flow.clients.elevenlabs_client.requests.post")
    @patch("reddit_flow.clients.elevenlabs_client.requests.get")
    def test_full_tts_workflow(self, mock_get, mock_post, elevenlabs_client):
        """Test complete workflow: check health, generate audio."""
        # Setup health check response
        health_response = MagicMock()
        health_response.status_code = 200
        mock_get.return_value = health_response

        # Setup TTS response
        tts_response = MagicMock()
        tts_response.status_code = 200
        tts_response.content = b"generated audio content"
        mock_post.return_value = tts_response

        # Verify service health
        assert elevenlabs_client.verify_service() is True

        # Generate audio
        audio = elevenlabs_client.text_to_speech("This is a test script.")

        assert len(audio) > 0
        assert isinstance(audio, bytes)
