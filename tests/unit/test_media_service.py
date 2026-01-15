"""
Unit tests for MediaService.

Tests cover:
- Service initialization
- Audio generation from text and scripts
- Audio upload to HeyGen
- Video generation workflow
- Complete media pipeline
- Status checking
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_flow.exceptions import MediaGenerationError, TTSError, VideoGenerationError
from reddit_flow.models import AudioAsset, VideoGenerationResponse, VideoScript
from reddit_flow.models.video import VideoStatus
from reddit_flow.services.media_service import MediaGenerationResult, MediaService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_elevenlabs_client():
    """Create a mock ElevenLabsClient."""
    client = MagicMock()
    client.text_to_speech = MagicMock(return_value=b"fake_audio_data")
    return client


@pytest.fixture
def mock_heygen_client():
    """Create a mock HeyGenClient."""
    client = MagicMock()
    client.upload_audio = MagicMock(
        return_value=AudioAsset(
            url="https://heygen.com/audio/123",
            asset_id="asset_123",
            file_size_bytes=1024,
        )
    )
    client.generate_video = MagicMock(return_value="video_123")
    client.wait_for_video = AsyncMock(return_value="https://heygen.com/video/123.mp4")
    client.check_video_status = MagicMock(
        return_value=VideoGenerationResponse(
            video_id="video_123",
            status=VideoStatus.COMPLETED,
            video_url="https://heygen.com/video/123.mp4",
        )
    )
    return client


@pytest.fixture
def media_service(mock_elevenlabs_client, mock_heygen_client, mock_prod_settings):
    """Create a MediaService with mock clients."""
    return MediaService(
        elevenlabs_client=mock_elevenlabs_client,
        heygen_client=mock_heygen_client,
        settings=mock_prod_settings,
    )


@pytest.fixture
def sample_video_script():
    """Create a sample VideoScript for testing."""
    return VideoScript(
        script="Hello world! This is a test script with enough words to be valid.",
        title="Test Video Title",
        source_post_id="abc123",
        source_subreddit="test",
    )


@pytest.fixture
def sample_audio_asset():
    """Create a sample AudioAsset for testing."""
    return AudioAsset(
        url="https://heygen.com/audio/456",
        asset_id="asset_456",
        file_size_bytes=2048,
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestMediaServiceInit:
    """Tests for MediaService initialization."""

    def test_init_default_values(self):
        """Test initialization with no clients."""
        with patch("reddit_flow.services.media_service.logger"):
            service = MediaService()
            assert service._elevenlabs_client is None
            assert service._heygen_client is None

    def test_init_with_clients(self, mock_elevenlabs_client, mock_heygen_client):
        """Test initialization with injected clients."""
        with patch("reddit_flow.services.media_service.logger"):
            service = MediaService(
                elevenlabs_client=mock_elevenlabs_client,
                heygen_client=mock_heygen_client,
            )
            assert service._elevenlabs_client is mock_elevenlabs_client
            assert service._heygen_client is mock_heygen_client

    def test_elevenlabs_client_property(self, mock_elevenlabs_client):
        """Test elevenlabs_client property returns injected client."""
        with patch("reddit_flow.services.media_service.logger"):
            service = MediaService(elevenlabs_client=mock_elevenlabs_client)
            assert service.elevenlabs_client is mock_elevenlabs_client

    def test_heygen_client_property(self, mock_heygen_client):
        """Test heygen_client property returns injected client."""
        with patch("reddit_flow.services.media_service.logger"):
            service = MediaService(heygen_client=mock_heygen_client)
            assert service.heygen_client is mock_heygen_client


# =============================================================================
# Audio Generation Tests
# =============================================================================


class TestGenerateAudio:
    """Tests for audio generation methods."""

    def test_generate_audio_success(self, media_service, mock_elevenlabs_client):
        """Test successful audio generation from text."""
        result = media_service.generate_audio("Hello world")

        assert result == b"fake_audio_data"
        mock_elevenlabs_client.text_to_speech.assert_called_once_with("Hello world")

    def test_generate_audio_empty_text_raises_error(self, media_service):
        """Test that empty text raises TTSError."""
        with pytest.raises(TTSError, match="empty text"):
            media_service.generate_audio("")

    def test_generate_audio_whitespace_only_raises_error(self, media_service):
        """Test that whitespace-only text raises TTSError."""
        with pytest.raises(TTSError, match="empty text"):
            media_service.generate_audio("   \n\t  ")

    def test_generate_audio_from_script_success(
        self, media_service, mock_elevenlabs_client, sample_video_script
    ):
        """Test audio generation from VideoScript."""
        result = media_service.generate_audio_from_script(sample_video_script)

        assert result == b"fake_audio_data"
        mock_elevenlabs_client.text_to_speech.assert_called_once_with(sample_video_script.script)

    def test_generate_audio_tts_error_propagates(self, media_service, mock_elevenlabs_client):
        """Test that TTS errors are propagated."""
        mock_elevenlabs_client.text_to_speech.side_effect = TTSError("TTS failed")

        with pytest.raises(TTSError, match="TTS failed"):
            media_service.generate_audio("Hello world")


# =============================================================================
# Audio Upload Tests
# =============================================================================


class TestUploadAudio:
    """Tests for audio upload methods."""

    def test_upload_audio_success(self, media_service, mock_heygen_client):
        """Test successful audio upload."""
        result = media_service.upload_audio(b"audio_data")

        assert isinstance(result, AudioAsset)
        assert result.url == "https://heygen.com/audio/123"
        mock_heygen_client.upload_audio.assert_called_once_with(b"audio_data")

    def test_upload_audio_empty_data_raises_error(self, media_service):
        """Test that empty audio data raises VideoGenerationError."""
        with pytest.raises(VideoGenerationError, match="empty audio"):
            media_service.upload_audio(b"")

    def test_upload_audio_error_propagates(self, media_service, mock_heygen_client):
        """Test that upload errors are propagated."""
        mock_heygen_client.upload_audio.side_effect = VideoGenerationError("Upload failed")

        with pytest.raises(VideoGenerationError, match="Upload failed"):
            media_service.upload_audio(b"audio_data")


# =============================================================================
# Video Generation Tests
# =============================================================================


class TestStartVideoGeneration:
    """Tests for starting video generation."""

    def test_start_video_generation_success(
        self, media_service, mock_heygen_client, sample_audio_asset
    ):
        """Test successful video generation start."""
        result = media_service.start_video_generation(
            audio_asset=sample_audio_asset,
            title="Test Video",
        )

        assert result == "video_123"
        mock_heygen_client.generate_video.assert_called_once_with(
            audio_url=sample_audio_asset.url,
            title="Test Video",
            avatar_id=None,
            test_mode=False,
        )

    def test_start_video_generation_with_avatar(
        self, media_service, mock_heygen_client, sample_audio_asset
    ):
        """Test video generation with custom avatar."""
        media_service.start_video_generation(
            audio_asset=sample_audio_asset,
            avatar_id="custom_avatar",
            test_mode=True,
        )

        mock_heygen_client.generate_video.assert_called_once_with(
            audio_url=sample_audio_asset.url,
            title=None,
            avatar_id="custom_avatar",
            test_mode=True,
        )

    def test_start_video_generation_error_propagates(
        self, media_service, mock_heygen_client, sample_audio_asset
    ):
        """Test that video generation errors are propagated."""
        mock_heygen_client.generate_video.side_effect = VideoGenerationError("Generation failed")

        with pytest.raises(VideoGenerationError, match="Generation failed"):
            media_service.start_video_generation(sample_audio_asset)


# =============================================================================
# Wait for Video Tests
# =============================================================================


class TestWaitForVideo:
    """Tests for waiting for video completion."""

    @pytest.mark.asyncio
    async def test_wait_for_video_success(self, media_service, mock_heygen_client):
        """Test successful video wait."""
        result = await media_service.wait_for_video("video_123")

        assert result == "https://heygen.com/video/123.mp4"
        mock_heygen_client.wait_for_video.assert_called_once_with(
            video_id="video_123",
            update_callback=None,
            timeout=None,
        )

    @pytest.mark.asyncio
    async def test_wait_for_video_with_callback(self, media_service, mock_heygen_client):
        """Test video wait with callback."""
        callback = AsyncMock()

        await media_service.wait_for_video("video_123", update_callback=callback)

        mock_heygen_client.wait_for_video.assert_called_once_with(
            video_id="video_123",
            update_callback=callback,
            timeout=None,
        )

    @pytest.mark.asyncio
    async def test_wait_for_video_with_timeout(self, media_service, mock_heygen_client):
        """Test video wait with custom timeout."""
        await media_service.wait_for_video("video_123", timeout=300)

        mock_heygen_client.wait_for_video.assert_called_once_with(
            video_id="video_123",
            update_callback=None,
            timeout=300,
        )

    @pytest.mark.asyncio
    async def test_wait_for_video_error_propagates(self, media_service, mock_heygen_client):
        """Test that wait errors are propagated."""
        mock_heygen_client.wait_for_video.side_effect = VideoGenerationError("Timeout")

        with pytest.raises(VideoGenerationError, match="Timeout"):
            await media_service.wait_for_video("video_123")


# =============================================================================
# Complete Workflow Tests
# =============================================================================


class TestGenerateVideoFromScript:
    """Tests for complete video generation workflow."""

    @pytest.mark.asyncio
    async def test_generate_video_from_script_success(
        self, media_service, mock_elevenlabs_client, mock_heygen_client, sample_video_script
    ):
        """Test successful complete workflow."""
        result = await media_service.generate_video_from_script(sample_video_script)

        assert isinstance(result, MediaGenerationResult)
        assert result.audio_data == b"fake_audio_data"
        assert result.audio_asset.url == "https://heygen.com/audio/123"
        assert result.video_id == "video_123"
        assert result.video_url == "https://heygen.com/video/123.mp4"

        mock_elevenlabs_client.text_to_speech.assert_called_once()
        mock_heygen_client.upload_audio.assert_called_once()
        mock_heygen_client.generate_video.assert_called_once()
        mock_heygen_client.wait_for_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_video_from_script_no_wait(
        self, media_service, mock_heygen_client, sample_video_script
    ):
        """Test workflow without waiting for completion."""
        result = await media_service.generate_video_from_script(
            sample_video_script,
            wait_for_completion=False,
        )

        assert result.video_id == "video_123"
        assert result.video_url is None
        mock_heygen_client.wait_for_video.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_video_from_script_with_options(
        self, media_service, mock_heygen_client, sample_video_script
    ):
        """Test workflow with custom options."""
        await media_service.generate_video_from_script(
            sample_video_script,
            avatar_id="custom_avatar",
            test_mode=True,
        )

        mock_heygen_client.generate_video.assert_called_once()
        call_kwargs = mock_heygen_client.generate_video.call_args.kwargs
        assert call_kwargs["avatar_id"] == "custom_avatar"
        assert call_kwargs["test_mode"] is True

    @pytest.mark.asyncio
    async def test_generate_video_from_script_with_callback(
        self, media_service, mock_heygen_client, sample_video_script
    ):
        """Test workflow with progress callback."""
        callback = AsyncMock()

        await media_service.generate_video_from_script(
            sample_video_script,
            update_callback=callback,
        )

        # Callback should be called for each step
        assert callback.await_count >= 3

    @pytest.mark.asyncio
    async def test_generate_video_from_script_tts_error(
        self, media_service, mock_elevenlabs_client, sample_video_script
    ):
        """Test that TTS errors are propagated."""
        mock_elevenlabs_client.text_to_speech.side_effect = TTSError("TTS failed")

        with pytest.raises(TTSError, match="TTS failed"):
            await media_service.generate_video_from_script(sample_video_script)

    @pytest.mark.asyncio
    async def test_generate_video_from_script_upload_error(
        self, media_service, mock_heygen_client, sample_video_script
    ):
        """Test that upload errors are propagated."""
        mock_heygen_client.upload_audio.side_effect = VideoGenerationError("Upload failed")

        with pytest.raises(VideoGenerationError, match="Upload failed"):
            await media_service.generate_video_from_script(sample_video_script)

    @pytest.mark.asyncio
    async def test_generate_video_from_script_generation_error(
        self, media_service, mock_heygen_client, sample_video_script
    ):
        """Test that generation errors are propagated."""
        mock_heygen_client.generate_video.side_effect = VideoGenerationError("Generation failed")

        with pytest.raises(VideoGenerationError, match="Generation failed"):
            await media_service.generate_video_from_script(sample_video_script)

    @pytest.mark.asyncio
    async def test_generate_video_from_script_unexpected_error(
        self, media_service, mock_elevenlabs_client, sample_video_script
    ):
        """Test that unexpected errors are wrapped."""
        mock_elevenlabs_client.text_to_speech.side_effect = RuntimeError("Unexpected")

        with pytest.raises(MediaGenerationError, match="Media generation failed"):
            await media_service.generate_video_from_script(sample_video_script)


# =============================================================================
# Generate from Text Tests
# =============================================================================


class TestGenerateVideoFromText:
    """Tests for generating video from plain text."""

    @pytest.mark.asyncio
    async def test_generate_video_from_text_success(
        self, media_service, mock_elevenlabs_client, mock_heygen_client
    ):
        """Test successful generation from plain text."""
        result = await media_service.generate_video_from_text(
            "Hello world! This is a test.",
            title="My Video",
        )

        assert isinstance(result, MediaGenerationResult)
        assert result.video_id == "video_123"
        mock_elevenlabs_client.text_to_speech.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_video_from_text_default_title(self, media_service, mock_heygen_client):
        """Test that default title is used."""
        await media_service.generate_video_from_text("Some text content here.")

        call_kwargs = mock_heygen_client.generate_video.call_args.kwargs
        assert call_kwargs["title"] == "Generated Video"

    @pytest.mark.asyncio
    async def test_generate_video_from_text_with_options(self, media_service, mock_heygen_client):
        """Test generation with custom options."""
        await media_service.generate_video_from_text(
            "Test content for video generation.",
            title="Custom Title",
            avatar_id="custom_avatar",
            test_mode=True,
            wait_for_completion=False,
        )

        mock_heygen_client.wait_for_video.assert_not_called()


# =============================================================================
# Status Check Tests
# =============================================================================


class TestCheckVideoStatus:
    """Tests for video status checking."""

    def test_check_video_status_success(self, media_service, mock_heygen_client):
        """Test successful status check."""
        result = media_service.check_video_status("video_123")

        assert result["video_id"] == "video_123"
        assert result["status"] == "completed"
        assert result["video_url"] == "https://heygen.com/video/123.mp4"
        mock_heygen_client.check_video_status.assert_called_once_with("video_123")

    def test_check_video_status_pending(self, media_service, mock_heygen_client):
        """Test status check for pending video."""
        mock_heygen_client.check_video_status.return_value = VideoGenerationResponse(
            video_id="video_456",
            status=VideoStatus.PROCESSING,
        )

        result = media_service.check_video_status("video_456")

        assert result["status"] == "processing"
        assert result["video_url"] is None

    def test_check_video_status_failed(self, media_service, mock_heygen_client):
        """Test status check for failed video."""
        mock_heygen_client.check_video_status.return_value = VideoGenerationResponse(
            video_id="video_789",
            status=VideoStatus.FAILED,
            error_message="Generation error",
        )

        result = media_service.check_video_status("video_789")

        assert result["status"] == "failed"
        assert result["error_message"] == "Generation error"

    def test_check_video_status_error_propagates(self, media_service, mock_heygen_client):
        """Test that status check errors are propagated."""
        mock_heygen_client.check_video_status.side_effect = VideoGenerationError(
            "Status check failed"
        )

        with pytest.raises(VideoGenerationError, match="Status check failed"):
            media_service.check_video_status("video_123")


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestMediaServiceIntegration:
    """Integration-like tests for MediaService workflows."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_all_callbacks(self, media_service, sample_video_script):
        """Test full workflow with progress tracking."""
        progress_updates = []

        async def track_progress(msg: str):
            progress_updates.append(msg)

        result = await media_service.generate_video_from_script(
            sample_video_script,
            update_callback=track_progress,
        )

        assert result.video_url is not None
        assert len(progress_updates) >= 3
        assert any("audio" in msg.lower() for msg in progress_updates)
        assert any("video" in msg.lower() for msg in progress_updates)

    @pytest.mark.asyncio
    async def test_workflow_test_mode(self, media_service, mock_heygen_client, sample_video_script):
        """Test workflow in test mode."""
        await media_service.generate_video_from_script(
            sample_video_script,
            test_mode=True,
        )

        call_kwargs = mock_heygen_client.generate_video.call_args.kwargs
        assert call_kwargs["test_mode"] is True

    @pytest.mark.asyncio
    async def test_workflow_preserves_script_title(
        self, media_service, mock_heygen_client, sample_video_script
    ):
        """Test that script title is used for video."""
        await media_service.generate_video_from_script(sample_video_script)

        call_kwargs = mock_heygen_client.generate_video.call_args.kwargs
        assert call_kwargs["title"] == sample_video_script.title
