"""
Unit tests for HeyGenClient.

Tests the HeyGen avatar video generation client with comprehensive
mocking of the requests library and async operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from reddit_flow.clients.heygen_client import HeyGenClient
from reddit_flow.exceptions import ConfigurationError, VideoGenerationError
from reddit_flow.models import AudioAsset, VideoGenerationRequest, VideoGenerationResponse

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def heygen_config():
    """Valid HeyGen client configuration."""
    return {
        "api_key": "test-api-key",
        "avatar_id": "test-avatar-id",
        "video_width": 1080,
        "video_height": 1920,
    }


@pytest.fixture
def heygen_client(heygen_config):
    """Create a HeyGenClient with valid config."""
    return HeyGenClient(config=heygen_config)


@pytest.fixture
def mock_upload_response():
    """Mock successful upload response."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": {
            "url": "https://heygen.com/audio/12345.mp3",
            "id": "asset-12345",
        }
    }
    return response


@pytest.fixture
def mock_generate_response():
    """Mock successful video generation response."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": {
            "video_id": "video-67890",
        }
    }
    return response


@pytest.fixture
def mock_status_completed_response():
    """Mock completed video status response."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": {
            "status": "completed",
            "video_url": "https://heygen.com/video/67890.mp4",
        }
    }
    return response


# =============================================================================
# Initialization Tests
# =============================================================================


class TestHeyGenClientInitialization:
    """Tests for HeyGenClient initialization."""

    def test_init_with_config(self, heygen_config):
        """Test initialization with explicit config."""
        client = HeyGenClient(config=heygen_config)

        assert client.is_initialized
        assert client.service_name == "HeyGen"
        assert client.avatar_id == "test-avatar-id"
        assert client.video_dimensions == (1080, 1920)

    def test_init_with_env_vars(self, monkeypatch):
        """Test initialization using environment variables."""
        monkeypatch.setenv("HEYGEN_API_KEY", "env-api-key")
        monkeypatch.setenv("HEYGEN_AVATAR_ID", "env-avatar-id")

        client = HeyGenClient()

        assert client.is_initialized
        assert client.avatar_id == "env-avatar-id"

    def test_init_missing_api_key_raises_error(self, monkeypatch):
        """Test that missing API key raises ConfigurationError."""
        monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
        monkeypatch.delenv("HEYGEN_AVATAR_ID", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            HeyGenClient(config={"avatar_id": "test"})

        assert "API key not found" in str(exc_info.value)

    def test_init_missing_avatar_id_raises_error(self, monkeypatch):
        """Test that missing avatar ID raises ConfigurationError."""
        monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
        monkeypatch.delenv("HEYGEN_AVATAR_ID", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            HeyGenClient(config={"api_key": "test"})

        assert "avatar ID not found" in str(exc_info.value)

    def test_init_with_custom_urls(self):
        """Test initialization with custom URLs."""
        config = {
            "api_key": "test-key",
            "avatar_id": "test-avatar",
            "base_url": "https://custom.heygen.com",
            "upload_url": "https://upload.custom.heygen.com",
        }

        client = HeyGenClient(config=config)

        assert client.base_url == "https://custom.heygen.com"
        assert client._upload_url == "https://upload.custom.heygen.com"

    def test_init_with_test_mode(self):
        """Test initialization with test mode enabled."""
        config = {
            "api_key": "test-key",
            "avatar_id": "test-avatar",
            "test_mode": True,
        }

        client = HeyGenClient(config=config)

        assert client._test_mode is True


# =============================================================================
# Health Check Tests
# =============================================================================


class TestHeyGenClientHealthCheck:
    """Tests for HeyGenClient health check."""

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_health_check_success(self, mock_get, heygen_client):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = heygen_client._health_check()

        assert result is True
        call_url = mock_get.call_args[0][0]
        assert "/v1/video.remaining_quota" in call_url

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_health_check_failure(self, mock_get, heygen_client):
        """Test health check with non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = heygen_client._health_check()

        assert result is False

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_health_check_exception(self, mock_get, heygen_client):
        """Test health check with network exception."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = heygen_client._health_check()

        assert result is False


# =============================================================================
# Upload Audio Tests
# =============================================================================


class TestHeyGenClientUploadAudio:
    """Tests for upload_audio method."""

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_upload_audio_returns_asset(self, mock_post, heygen_client, mock_upload_response):
        """Test successful audio upload returns AudioAsset."""
        mock_post.return_value = mock_upload_response

        result = heygen_client.upload_audio(b"audio bytes")

        assert isinstance(result, AudioAsset)
        assert result.url == "https://heygen.com/audio/12345.mp3"
        assert result.asset_id == "asset-12345"
        assert result.file_size_bytes == len(b"audio bytes")

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_upload_audio_sends_correct_headers(
        self, mock_post, heygen_client, mock_upload_response
    ):
        """Test that correct headers are sent."""
        mock_post.return_value = mock_upload_response

        heygen_client.upload_audio(b"audio bytes")

        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["X-API-KEY"] == "test-api-key"
        assert headers["Content-Type"] == "audio/mpeg"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_upload_audio_custom_content_type(self, mock_post, heygen_client, mock_upload_response):
        """Test upload with custom content type."""
        mock_post.return_value = mock_upload_response

        heygen_client.upload_audio(b"wav bytes", content_type="audio/wav")

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Content-Type"] == "audio/wav"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_upload_audio_url_returns_string(self, mock_post, heygen_client, mock_upload_response):
        """Test backward-compatible upload_audio_url method."""
        mock_post.return_value = mock_upload_response

        result = heygen_client.upload_audio_url(b"audio bytes")

        assert isinstance(result, str)
        assert result == "https://heygen.com/audio/12345.mp3"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_upload_audio_http_error_raises_video_error(self, mock_post, heygen_client):
        """Test that HTTP errors are wrapped in VideoGenerationError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with pytest.raises(VideoGenerationError) as exc_info:
            heygen_client.upload_audio(b"audio")

        assert "upload failed" in str(exc_info.value)

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_upload_audio_network_error_raises_video_error(self, mock_post, heygen_client):
        """Test that network errors are wrapped in VideoGenerationError."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        with pytest.raises(VideoGenerationError) as exc_info:
            heygen_client.upload_audio(b"audio")

        assert "Network error" in str(exc_info.value)


# =============================================================================
# Generate Video Tests
# =============================================================================


class TestHeyGenClientGenerateVideo:
    """Tests for generate_video method."""

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_returns_id(self, mock_post, heygen_client, mock_generate_response):
        """Test successful video generation returns video ID."""
        mock_post.return_value = mock_generate_response

        result = heygen_client.generate_video("https://audio.url/test.mp3")

        assert result == "video-67890"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_with_title(self, mock_post, heygen_client, mock_generate_response):
        """Test video generation with title."""
        mock_post.return_value = mock_generate_response

        heygen_client.generate_video("https://audio.url/test.mp3", title="My Video")

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["json"]
        assert data["title"] == "My Video"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_uses_default_avatar(
        self, mock_post, heygen_client, mock_generate_response
    ):
        """Test that default avatar ID is used."""
        mock_post.return_value = mock_generate_response

        heygen_client.generate_video("https://audio.url/test.mp3")

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["json"]
        assert data["video_inputs"][0]["character"]["avatar_id"] == "test-avatar-id"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_override_avatar(self, mock_post, heygen_client, mock_generate_response):
        """Test video generation with overridden avatar."""
        mock_post.return_value = mock_generate_response

        heygen_client.generate_video("https://audio.url/test.mp3", avatar_id="custom-avatar")

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["json"]
        assert data["video_inputs"][0]["character"]["avatar_id"] == "custom-avatar"

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_test_mode(self, mock_post, mock_generate_response):
        """Test video generation in test mode."""
        config = {
            "api_key": "test-key",
            "avatar_id": "test-avatar",
            "test_mode": True,
        }
        client = HeyGenClient(config=config)
        mock_post.return_value = mock_generate_response

        client.generate_video("https://audio.url/test.mp3")

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["json"]
        assert data["test"] is True

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_sets_dimensions(self, mock_post, heygen_client, mock_generate_response):
        """Test that video dimensions are set correctly."""
        mock_post.return_value = mock_generate_response

        heygen_client.generate_video("https://audio.url/test.mp3")

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["json"]
        assert data["dimension"]["width"] == 1080
        assert data["dimension"]["height"] == 1920

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_video_http_error_raises_video_error(self, mock_post, heygen_client):
        """Test that HTTP errors are wrapped in VideoGenerationError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request"
        mock_post.return_value = mock_response
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with pytest.raises(VideoGenerationError) as exc_info:
            heygen_client.generate_video("https://audio.url/test.mp3")

        assert "generation failed" in str(exc_info.value)


# =============================================================================
# Generate Video from Request Tests
# =============================================================================


class TestHeyGenClientGenerateVideoFromRequest:
    """Tests for generate_video_from_request method."""

    @patch("reddit_flow.clients.heygen_client.requests.post")
    def test_generate_from_request(self, mock_post, heygen_client, mock_generate_response):
        """Test video generation from request model."""
        mock_post.return_value = mock_generate_response

        request = VideoGenerationRequest(
            audio_url="https://audio.url/test.mp3",
            avatar_id="request-avatar",
            title="Request Title",
            test_mode=True,
        )

        result = heygen_client.generate_video_from_request(request)

        assert result == "video-67890"
        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["json"]
        assert data["title"] == "Request Title"
        assert data["test"] is True


# =============================================================================
# Check Video Status Tests
# =============================================================================


class TestHeyGenClientCheckVideoStatus:
    """Tests for check_video_status method."""

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_check_status_completed(self, mock_get, heygen_client, mock_status_completed_response):
        """Test checking completed video status."""
        mock_get.return_value = mock_status_completed_response

        result = heygen_client.check_video_status("video-123")

        assert isinstance(result, VideoGenerationResponse)
        assert result.video_id == "video-123"
        assert result.status == "completed"
        assert result.video_url == "https://heygen.com/video/67890.mp4"

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_check_status_pending(self, mock_get, heygen_client):
        """Test checking pending video status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "status": "processing",
            }
        }
        mock_get.return_value = mock_response

        result = heygen_client.check_video_status("video-123")

        assert result.status == "processing"
        assert result.video_url is None

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_check_status_failed(self, mock_get, heygen_client):
        """Test checking failed video status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "status": "failed",
                "error": "Generation failed",
            }
        }
        mock_get.return_value = mock_response

        result = heygen_client.check_video_status("video-123")

        assert result.status == "failed"
        assert result.error_message == "Generation failed"

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_check_status_http_error(self, mock_get, heygen_client):
        """Test that HTTP errors raise VideoGenerationError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with pytest.raises(VideoGenerationError):
            heygen_client.check_video_status("video-123")


# =============================================================================
# Wait for Video Tests
# =============================================================================


class TestHeyGenClientWaitForVideo:
    """Tests for wait_for_video async method."""

    @pytest.mark.asyncio
    @patch("reddit_flow.clients.heygen_client.requests.get")
    async def test_wait_for_video_immediate_completion(
        self, mock_get, heygen_client, mock_status_completed_response
    ):
        """Test waiting for video that completes immediately."""
        mock_get.return_value = mock_status_completed_response

        result = await heygen_client.wait_for_video("video-123")

        assert result == "https://heygen.com/video/67890.mp4"

    @pytest.mark.asyncio
    @patch("reddit_flow.clients.heygen_client.asyncio.sleep", new_callable=AsyncMock)
    @patch("reddit_flow.clients.heygen_client.requests.get")
    async def test_wait_for_video_eventual_completion(self, mock_get, mock_sleep, heygen_client):
        """Test waiting for video that completes after polling."""
        # First call returns processing, second returns completed
        processing_response = MagicMock()
        processing_response.status_code = 200
        processing_response.json.return_value = {"data": {"status": "processing"}}

        completed_response = MagicMock()
        completed_response.status_code = 200
        completed_response.json.return_value = {
            "data": {
                "status": "completed",
                "video_url": "https://heygen.com/video/final.mp4",
            }
        }

        mock_get.side_effect = [processing_response, completed_response]

        result = await heygen_client.wait_for_video("video-123")

        assert result == "https://heygen.com/video/final.mp4"
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    @patch("reddit_flow.clients.heygen_client.requests.get")
    async def test_wait_for_video_failure(self, mock_get, heygen_client):
        """Test waiting for video that fails."""
        failed_response = MagicMock()
        failed_response.status_code = 200
        failed_response.json.return_value = {
            "data": {
                "status": "failed",
                "error": "Avatar unavailable",
            }
        }
        mock_get.return_value = failed_response

        with pytest.raises(VideoGenerationError) as exc_info:
            await heygen_client.wait_for_video("video-123")

        assert "Avatar unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("reddit_flow.clients.heygen_client.time.time")
    @patch("reddit_flow.clients.heygen_client.requests.get")
    async def test_wait_for_video_timeout(self, mock_get, mock_time, heygen_client):
        """Test waiting for video that times out."""
        # Simulate timeout by making time.time() return increasing values
        mock_time.side_effect = [0, 0, 700, 700]  # Start, check, elapsed check, elapsed check

        processing_response = MagicMock()
        processing_response.status_code = 200
        processing_response.json.return_value = {"data": {"status": "processing"}}
        mock_get.return_value = processing_response

        with pytest.raises(VideoGenerationError) as exc_info:
            await heygen_client.wait_for_video("video-123", timeout=600)

        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("reddit_flow.clients.heygen_client.requests.get")
    async def test_wait_for_video_with_callback(
        self, mock_get, heygen_client, mock_status_completed_response
    ):
        """Test waiting with status update callback."""
        mock_get.return_value = mock_status_completed_response
        callback = AsyncMock()

        await heygen_client.wait_for_video("video-123", update_callback=callback)

        # Callback not called since video completed immediately
        # (callback is called during polling loop before completion)


# =============================================================================
# Get Remaining Quota Tests
# =============================================================================


class TestHeyGenClientGetRemainingQuota:
    """Tests for get_remaining_quota method."""

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_get_quota_success(self, mock_get, heygen_client):
        """Test successful quota retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "remaining_quota": 100,
                "plan": "pro",
            }
        }
        mock_get.return_value = mock_response

        result = heygen_client.get_remaining_quota()

        assert result["remaining_quota"] == 100
        assert result["plan"] == "pro"

    @patch("reddit_flow.clients.heygen_client.requests.get")
    def test_get_quota_error(self, mock_get, heygen_client):
        """Test quota retrieval error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with pytest.raises(VideoGenerationError):
            heygen_client.get_remaining_quota()


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestHeyGenClientIntegration:
    """Integration-style tests for the full workflow."""

    @pytest.mark.asyncio
    @patch("reddit_flow.clients.heygen_client.requests.get")
    @patch("reddit_flow.clients.heygen_client.requests.post")
    async def test_full_video_generation_workflow(self, mock_post, mock_get, heygen_client):
        """Test complete workflow: upload, generate, wait."""
        # Setup upload response
        upload_response = MagicMock()
        upload_response.status_code = 200
        upload_response.json.return_value = {
            "data": {"url": "https://heygen.com/audio/test.mp3", "id": "asset-1"}
        }

        # Setup generate response
        generate_response = MagicMock()
        generate_response.status_code = 200
        generate_response.json.return_value = {"data": {"video_id": "video-1"}}

        mock_post.side_effect = [upload_response, generate_response]

        # Setup status response (completed)
        status_response = MagicMock()
        status_response.status_code = 200
        status_response.json.return_value = {
            "data": {
                "status": "completed",
                "video_url": "https://heygen.com/video/final.mp4",
            }
        }
        mock_get.return_value = status_response

        # Execute workflow
        audio_asset = heygen_client.upload_audio(b"test audio bytes")
        video_id = heygen_client.generate_video(audio_asset.url, title="Test Video")
        video_url = await heygen_client.wait_for_video(video_id)

        assert audio_asset.url == "https://heygen.com/audio/test.mp3"
        assert video_id == "video-1"
        assert video_url == "https://heygen.com/video/final.mp4"
