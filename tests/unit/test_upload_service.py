"""
Unit tests for UploadService.

Tests cover:
- Service initialization
- Video upload from local files
- Video upload with VideoScript metadata
- Video download and upload from URLs
- Title and description formatting
- Video info retrieval and deletion
- Error handling
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reddit_flow.exceptions import YouTubeUploadError
from reddit_flow.models import VideoScript, YouTubeUploadResponse
from reddit_flow.services.upload_service import UploadResult, UploadService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_youtube_client():
    """Create a mock YouTubeClient."""
    client = MagicMock()
    client.upload_video_from_request = MagicMock(
        return_value=YouTubeUploadResponse(
            video_id="abc123",
            title="Test Video",
            url="https://youtube.com/watch?v=abc123",
        )
    )
    client.get_video_info = MagicMock(
        return_value={
            "id": "abc123",
            "snippet": {"title": "Test Video"},
            "status": {"privacyStatus": "public"},
        }
    )
    client.delete_video = MagicMock(return_value=True)
    return client


@pytest.fixture
def upload_service(mock_youtube_client):
    """Create an UploadService with mock client."""
    return UploadService(
        youtube_client=mock_youtube_client,
        default_category_id="22",
        default_privacy="public",
    )


@pytest.fixture
def sample_video_script():
    """Create a sample VideoScript for testing."""
    return VideoScript(
        script="Hello world! This is a test script with enough words to be valid.",
        title="Amazing Reddit Story",
        source_post_id="xyz789",
        source_subreddit="AskReddit",
        user_opinion="I found this really interesting!",
    )


@pytest.fixture
def temp_video_file():
    """Create a temporary video file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake video content")
        temp_path = f.name
    yield temp_path
    # Cleanup
    try:
        Path(temp_path).unlink()
    except FileNotFoundError:
        pass


# =============================================================================
# Initialization Tests
# =============================================================================


class TestUploadServiceInit:
    """Tests for UploadService initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        with patch("reddit_flow.services.upload_service.logger"):
            service = UploadService()
            assert service._youtube_client is None
            assert service._default_category_id == "22"
            assert service._default_privacy == "public"

    def test_init_custom_values(self, mock_youtube_client):
        """Test initialization with custom values."""
        with patch("reddit_flow.services.upload_service.logger"):
            service = UploadService(
                youtube_client=mock_youtube_client,
                default_category_id="24",
                default_privacy="unlisted",
            )
            assert service._youtube_client is mock_youtube_client
            assert service._default_category_id == "24"
            assert service._default_privacy == "unlisted"

    def test_youtube_client_property(self, mock_youtube_client):
        """Test youtube_client property returns injected client."""
        with patch("reddit_flow.services.upload_service.logger"):
            service = UploadService(youtube_client=mock_youtube_client)
            assert service.youtube_client is mock_youtube_client


# =============================================================================
# Upload Video Tests
# =============================================================================


class TestUploadVideo:
    """Tests for video upload methods."""

    def test_upload_video_success(self, upload_service, mock_youtube_client, temp_video_file):
        """Test successful video upload."""
        result = upload_service.upload_video(
            file_path=temp_video_file,
            title="Test Video",
            description="Test description",
        )

        assert isinstance(result, YouTubeUploadResponse)
        assert result.video_id == "abc123"
        mock_youtube_client.upload_video_from_request.assert_called_once()

    def test_upload_video_file_not_found(self, upload_service):
        """Test upload with non-existent file."""
        with pytest.raises(YouTubeUploadError, match="Video file not found"):
            upload_service.upload_video(
                file_path="/nonexistent/video.mp4",
                title="Test Video",
            )

    def test_upload_video_with_tags(self, upload_service, mock_youtube_client, temp_video_file):
        """Test upload with tags."""
        upload_service.upload_video(
            file_path=temp_video_file,
            title="Test Video",
            tags=["test", "video", "sample"],
        )

        call_args = mock_youtube_client.upload_video_from_request.call_args
        request = call_args.kwargs["request"]
        assert request.tags == ["test", "video", "sample"]

    def test_upload_video_with_privacy(self, upload_service, mock_youtube_client, temp_video_file):
        """Test upload with custom privacy setting."""
        upload_service.upload_video(
            file_path=temp_video_file,
            title="Test Video",
            privacy_status="unlisted",
        )

        call_args = mock_youtube_client.upload_video_from_request.call_args
        request = call_args.kwargs["request"]
        assert request.privacy_status == "unlisted"

    def test_upload_video_with_progress_callback(
        self, upload_service, mock_youtube_client, temp_video_file
    ):
        """Test upload with progress callback."""
        callback = MagicMock()

        upload_service.upload_video(
            file_path=temp_video_file,
            title="Test Video",
            progress_callback=callback,
        )

        call_args = mock_youtube_client.upload_video_from_request.call_args
        assert call_args.kwargs["progress_callback"] is callback

    def test_upload_video_error_propagates(
        self, upload_service, mock_youtube_client, temp_video_file
    ):
        """Test that upload errors are propagated."""
        mock_youtube_client.upload_video_from_request.side_effect = YouTubeUploadError(
            "Upload failed"
        )

        with pytest.raises(YouTubeUploadError, match="Upload failed"):
            upload_service.upload_video(
                file_path=temp_video_file,
                title="Test Video",
            )


# =============================================================================
# Upload from Script Tests
# =============================================================================


class TestUploadFromScript:
    """Tests for uploading with VideoScript metadata."""

    def test_upload_from_script_success(
        self, upload_service, mock_youtube_client, temp_video_file, sample_video_script
    ):
        """Test successful upload using script metadata."""
        result = upload_service.upload_from_script(
            file_path=temp_video_file,
            script=sample_video_script,
        )

        assert isinstance(result, YouTubeUploadResponse)
        assert result.video_id == "abc123"

    def test_upload_from_script_uses_youtube_title(
        self, upload_service, mock_youtube_client, temp_video_file, sample_video_script
    ):
        """Test that youtube_title is used from script."""
        upload_service.upload_from_script(
            file_path=temp_video_file,
            script=sample_video_script,
        )

        call_args = mock_youtube_client.upload_video_from_request.call_args
        request = call_args.kwargs["request"]
        # youtube_title is computed from title, check it's used
        assert "Reddit Story" in request.title or "Amazing" in request.title

    def test_upload_from_script_with_additional_description(
        self, upload_service, mock_youtube_client, temp_video_file, sample_video_script
    ):
        """Test upload with additional description text."""
        upload_service.upload_from_script(
            file_path=temp_video_file,
            script=sample_video_script,
            additional_description="Subscribe for more!",
        )

        call_args = mock_youtube_client.upload_video_from_request.call_args
        request = call_args.kwargs["request"]
        assert "Subscribe for more!" in request.description

    def test_upload_from_script_includes_source_info(
        self, upload_service, mock_youtube_client, temp_video_file, sample_video_script
    ):
        """Test that source subreddit is included in description."""
        upload_service.upload_from_script(
            file_path=temp_video_file,
            script=sample_video_script,
        )

        call_args = mock_youtube_client.upload_video_from_request.call_args
        request = call_args.kwargs["request"]
        assert "r/AskReddit" in request.description


# =============================================================================
# Upload from URL Tests
# =============================================================================


class TestUploadFromUrl:
    """Tests for downloading and uploading from URLs."""

    def test_upload_from_url_success(self, upload_service, mock_youtube_client):
        """Test successful download and upload from URL."""
        with patch.object(
            upload_service, "_download_video", return_value="/tmp/video.mp4"
        ) as mock_download:
            with patch.object(upload_service, "_cleanup_file") as mock_cleanup:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.stat") as mock_stat:
                        mock_stat.return_value.st_size = 1024 * 1024

                        result = upload_service.upload_from_url(
                            video_url="https://example.com/video.mp4",
                            title="Downloaded Video",
                        )

                        assert isinstance(result, UploadResult)
                        assert result.video_id == "abc123"
                        mock_download.assert_called_once()
                        mock_cleanup.assert_called_once()

    def test_upload_from_url_keep_local_file(self, upload_service, mock_youtube_client):
        """Test upload from URL keeping the local file."""
        with patch.object(upload_service, "_download_video", return_value="/tmp/video.mp4"):
            with patch.object(upload_service, "_cleanup_file") as mock_cleanup:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.stat") as mock_stat:
                        mock_stat.return_value.st_size = 1024 * 1024

                        result = upload_service.upload_from_url(
                            video_url="https://example.com/video.mp4",
                            title="Downloaded Video",
                            keep_local_file=True,
                        )

                        assert result.local_file_path == "/tmp/video.mp4"
                        mock_cleanup.assert_not_called()

    def test_upload_from_url_cleanup_on_error(self, upload_service, mock_youtube_client):
        """Test that file is cleaned up on upload error."""
        mock_youtube_client.upload_video_from_request.side_effect = YouTubeUploadError(
            "Upload failed"
        )

        with patch.object(upload_service, "_download_video", return_value="/tmp/video.mp4"):
            with patch.object(upload_service, "_cleanup_file") as mock_cleanup:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.stat") as mock_stat:
                        mock_stat.return_value.st_size = 1024 * 1024

                        with pytest.raises(YouTubeUploadError):
                            upload_service.upload_from_url(
                                video_url="https://example.com/video.mp4",
                                title="Downloaded Video",
                            )

                        mock_cleanup.assert_called_once()


# =============================================================================
# Upload from URL with Script Tests
# =============================================================================


class TestUploadFromUrlWithScript:
    """Tests for downloading and uploading with script metadata."""

    def test_upload_from_url_with_script_success(
        self, upload_service, mock_youtube_client, sample_video_script
    ):
        """Test successful download and upload with script metadata."""
        with patch.object(upload_service, "_download_video", return_value="/tmp/video.mp4"):
            with patch.object(upload_service, "_cleanup_file"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.stat") as mock_stat:
                        mock_stat.return_value.st_size = 1024 * 1024

                        result = upload_service.upload_from_url_with_script(
                            video_url="https://example.com/video.mp4",
                            script=sample_video_script,
                        )

                        assert isinstance(result, UploadResult)
                        assert result.video_id == "abc123"


# =============================================================================
# Format Title Tests
# =============================================================================


class TestFormatTitle:
    """Tests for title formatting."""

    def test_format_title_normal(self, upload_service):
        """Test formatting a normal title."""
        result = upload_service._format_title("My Video Title")
        assert result == "My Video Title"

    def test_format_title_empty(self, upload_service):
        """Test formatting an empty title."""
        result = upload_service._format_title("")
        assert result == "Untitled Video"

    def test_format_title_too_long(self, upload_service):
        """Test formatting a title that exceeds limit."""
        long_title = "A" * 150
        result = upload_service._format_title(long_title)
        assert len(result) == 100
        assert result.endswith("...")

    def test_format_title_strips_whitespace(self, upload_service):
        """Test that whitespace is stripped."""
        result = upload_service._format_title("  Title with spaces  ")
        assert result == "Title with spaces"

    def test_format_title_exactly_100_chars(self, upload_service):
        """Test title exactly at limit."""
        title = "A" * 100
        result = upload_service._format_title(title)
        assert len(result) == 100
        assert not result.endswith("...")


# =============================================================================
# Format Description Tests
# =============================================================================


class TestFormatDescription:
    """Tests for description formatting."""

    def test_format_description_normal(self, upload_service):
        """Test formatting a normal description."""
        result = upload_service._format_description("This is a description")
        assert result == "This is a description"

    def test_format_description_empty(self, upload_service):
        """Test formatting an empty description."""
        result = upload_service._format_description("")
        assert result == ""

    def test_format_description_too_long(self, upload_service):
        """Test formatting a description that exceeds limit."""
        long_desc = "A" * 6000
        result = upload_service._format_description(long_desc)
        assert len(result) == 5000
        assert result.endswith("...")

    def test_format_description_strips_whitespace(self, upload_service):
        """Test that whitespace is stripped."""
        result = upload_service._format_description("  Description  ")
        assert result == "Description"


# =============================================================================
# Build Description from Script Tests
# =============================================================================


class TestBuildDescriptionFromScript:
    """Tests for building descriptions from VideoScript."""

    def test_build_description_includes_subreddit(self, upload_service, sample_video_script):
        """Test that subreddit is included."""
        result = upload_service._build_description_from_script(sample_video_script)
        assert "r/AskReddit" in result

    def test_build_description_includes_post_id(self, upload_service, sample_video_script):
        """Test that post ID is included."""
        result = upload_service._build_description_from_script(sample_video_script)
        assert "xyz789" in result

    def test_build_description_includes_script_summary(self, upload_service, sample_video_script):
        """Test that script summary is included."""
        result = upload_service._build_description_from_script(sample_video_script)
        assert "Hello world" in result

    def test_build_description_includes_user_opinion(self, upload_service, sample_video_script):
        """Test that user opinion is included."""
        result = upload_service._build_description_from_script(sample_video_script)
        assert "really interesting" in result

    def test_build_description_includes_additional_text(self, upload_service, sample_video_script):
        """Test that additional text is included."""
        result = upload_service._build_description_from_script(
            sample_video_script, "Subscribe for more!"
        )
        assert "Subscribe for more!" in result

    def test_build_description_includes_ai_notice(self, upload_service, sample_video_script):
        """Test that AI generation notice is included."""
        result = upload_service._build_description_from_script(sample_video_script)
        assert "Generated with AI" in result


# =============================================================================
# Download Video Tests
# =============================================================================


class TestDownloadVideo:
    """Tests for video download functionality."""

    def test_download_video_success(self, upload_service):
        """Test successful video download."""
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"video", b"data"]
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = upload_service._download_video("https://example.com/video.mp4")

            assert result.endswith(".mp4")
            # Clean up
            Path(result).unlink()

    def test_download_video_request_error(self, upload_service):
        """Test download with request error."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.RequestException("Failed")):
            with pytest.raises(YouTubeUploadError, match="Failed to download"):
                upload_service._download_video("https://example.com/video.mp4")


# =============================================================================
# Video Info and Delete Tests
# =============================================================================


class TestVideoInfoAndDelete:
    """Tests for video info retrieval and deletion."""

    def test_get_video_info(self, upload_service, mock_youtube_client):
        """Test getting video info."""
        result = upload_service.get_video_info("abc123")

        assert result["id"] == "abc123"
        mock_youtube_client.get_video_info.assert_called_once_with("abc123")

    def test_delete_video(self, upload_service, mock_youtube_client):
        """Test deleting a video."""
        result = upload_service.delete_video("abc123")

        assert result is True
        mock_youtube_client.delete_video.assert_called_once_with("abc123")

    def test_delete_video_error(self, upload_service, mock_youtube_client):
        """Test delete with error."""
        mock_youtube_client.delete_video.side_effect = YouTubeUploadError("Delete failed")

        with pytest.raises(YouTubeUploadError, match="Delete failed"):
            upload_service.delete_video("abc123")


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanupFile:
    """Tests for file cleanup functionality."""

    def test_cleanup_existing_file(self, upload_service, temp_video_file):
        """Test cleanup of existing file."""
        assert Path(temp_video_file).exists()
        upload_service._cleanup_file(temp_video_file)
        assert not Path(temp_video_file).exists()

    def test_cleanup_nonexistent_file(self, upload_service):
        """Test cleanup of non-existent file (no error)."""
        # Should not raise
        upload_service._cleanup_file("/nonexistent/file.mp4")


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestUploadServiceIntegration:
    """Integration-like tests for UploadService workflows."""

    def test_full_upload_workflow(
        self, upload_service, mock_youtube_client, temp_video_file, sample_video_script
    ):
        """Test complete upload workflow with script."""
        result = upload_service.upload_from_script(
            file_path=temp_video_file,
            script=sample_video_script,
            additional_description="Like and subscribe!",
            tags=["reddit", "story"],
            privacy_status="unlisted",
        )

        assert result.video_id == "abc123"

        call_args = mock_youtube_client.upload_video_from_request.call_args
        request = call_args.kwargs["request"]
        assert request.privacy_status == "unlisted"
        assert request.tags == ["reddit", "story"]
        assert "r/AskReddit" in request.description
        assert "Like and subscribe!" in request.description
