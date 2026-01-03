"""
Unit tests for YouTubeClient.

Tests cover:
- Initialization and configuration
- OAuth2 authentication flow
- Video upload functionality
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from reddit_flow.clients.youtube_client import YouTubeClient
from reddit_flow.exceptions import YouTubeUploadError
from reddit_flow.models import YouTubeUploadRequest, YouTubeUploadResponse


class TestYouTubeClientInitialization:
    """Tests for YouTubeClient initialization."""

    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_init_with_config(self, mock_exists):
        """Test initialization with explicit config."""
        mock_exists.return_value = True

        client = YouTubeClient(
            {
                "client_secrets_file": "my-secrets.json",
                "token_file": "my-token.json",
                "category_id": "24",
                "chunk_size": 2 * 1024 * 1024,
            }
        )

        assert client._client_secrets_file == "my-secrets.json"
        assert client._token_file == "my-token.json"
        assert client._category_id == "24"
        assert client._chunk_size == 2 * 1024 * 1024
        assert client._service is None  # Lazy loaded

    @patch.dict(
        "os.environ",
        {
            "YOUTUBE_CLIENT_SECRETS_FILE": "env-secrets.json",
            "YOUTUBE_CATEGORY_ID": "28",
        },
    )
    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_init_with_env_vars(self, mock_exists):
        """Test initialization from environment variables."""
        mock_exists.return_value = True

        client = YouTubeClient()

        assert client._client_secrets_file == "env-secrets.json"
        assert client._category_id == "28"

    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_init_with_defaults(self, mock_exists):
        """Test initialization with default values."""
        mock_exists.return_value = True

        with patch.dict("os.environ", {}, clear=True):
            client = YouTubeClient()

        assert client._client_secrets_file == "youtube-client.json"
        assert client._token_file == "token.json"
        assert client._category_id == "22"
        assert client._chunk_size == 1024 * 1024

    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_init_service_not_loaded(self, mock_exists):
        """Test that service is not loaded until needed."""
        mock_exists.return_value = True

        client = YouTubeClient()

        assert client._service is None
        assert client.is_initialized is True


class TestYouTubeClientAuthentication:
    """Tests for YouTube OAuth2 authentication."""

    @patch("reddit_flow.clients.youtube_client.Path")
    def test_get_service_secrets_not_found(self, mock_path_class):
        """Test error when client secrets file is missing."""
        # Mock Path to return False for secrets existence
        mock_secrets_path = MagicMock()
        mock_secrets_path.exists.return_value = False
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False

        def path_factory(arg):
            if "secrets" in str(arg) or "youtube-client" in str(arg):
                return mock_secrets_path
            return mock_token_path

        mock_path_class.side_effect = path_factory

        client = YouTubeClient.__new__(YouTubeClient)
        client._config = {}
        client._secrets_path = mock_secrets_path
        client._token_path = mock_token_path
        client._service = None
        client.SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

        with pytest.raises(YouTubeUploadError) as exc_info:
            client._get_authenticated_service()

        assert "client secrets file not found" in str(exc_info.value).lower()

    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_get_service_loads_existing_token(self, mock_path_exists):
        """Test that existing valid token is loaded."""
        mock_path_exists.return_value = True

        # Mock Google libraries
        with patch(
            "reddit_flow.clients.youtube_client.YouTubeClient._get_authenticated_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service

            client = YouTubeClient()
            service = client._get_authenticated_service()

            assert service == mock_service

    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_health_check_success(self, mock_exists):
        """Test health check with valid authentication."""
        mock_exists.return_value = True

        client = YouTubeClient()

        with patch.object(client, "_get_authenticated_service") as mock_auth:
            mock_auth.return_value = MagicMock()
            result = client._health_check()

        assert result is True

    @patch("reddit_flow.clients.youtube_client.Path.exists")
    def test_health_check_failure(self, mock_exists):
        """Test health check when authentication fails."""
        mock_exists.return_value = True

        client = YouTubeClient()

        with patch.object(client, "_get_authenticated_service") as mock_auth:
            mock_auth.side_effect = YouTubeUploadError("Auth failed")
            result = client._health_check()

        assert result is False


class TestYouTubeClientUpload:
    """Tests for video upload functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock YouTube client for testing."""
        with patch("reddit_flow.clients.youtube_client.Path.exists") as mock_exists:
            mock_exists.return_value = True
            client = YouTubeClient({"category_id": "22"})
            return client

    def test_upload_video_success(self, mock_client, tmp_path):
        """Test successful video upload."""
        # Create a test video file
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        # Mock the service and upload
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "abc123xyz"})
        mock_service.videos().insert.return_value = mock_request

        mock_media_upload = MagicMock()

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload", return_value=mock_media_upload):
                video_id = mock_client.upload_video(
                    file_path=str(video_file),
                    title="Test Video",
                    description="Test description",
                )

        assert video_id == "abc123xyz"

    def test_upload_video_with_progress_callback(self, mock_client, tmp_path):
        """Test upload with progress callback."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        mock_service = MagicMock()
        mock_request = MagicMock()

        # Simulate chunked upload progress
        mock_status = MagicMock()
        mock_status.progress.side_effect = [0.5, 1.0]
        mock_request.next_chunk.side_effect = [
            (mock_status, None),  # 50% progress
            (None, {"id": "xyz789"}),  # Complete
        ]
        mock_service.videos().insert.return_value = mock_request

        progress_values = []

        def progress_callback(progress):
            progress_values.append(progress)

        mock_media_upload = MagicMock()

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload", return_value=mock_media_upload):
                video_id = mock_client.upload_video(
                    file_path=str(video_file),
                    title="Test Video",
                    description="Test description",
                    progress_callback=progress_callback,
                )

        assert video_id == "xyz789"
        assert 50 in progress_values

    def test_upload_video_file_not_found(self, mock_client):
        """Test error when video file doesn't exist."""
        # Mock _get_authenticated_service to prevent actual auth
        with patch.object(mock_client, "_get_authenticated_service", return_value=MagicMock()):
            with patch("googleapiclient.http.MediaFileUpload"):
                with pytest.raises(YouTubeUploadError) as exc_info:
                    mock_client.upload_video(
                        file_path="/nonexistent/video.mp4",
                        title="Test",
                        description="Test",
                    )

        assert "not found" in str(exc_info.value).lower()

    def test_upload_video_title_truncation(self, mock_client, tmp_path):
        """Test that long titles are truncated to 100 chars."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "abc123"})
        mock_service.videos().insert.return_value = mock_request

        long_title = "A" * 150  # 150 characters

        mock_media_upload = MagicMock()

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload", return_value=mock_media_upload):
                mock_client.upload_video(
                    file_path=str(video_file),
                    title=long_title,
                    description="Test",
                )

        # Verify title was truncated in the API call
        call_kwargs = mock_service.videos().insert.call_args
        body = call_kwargs[1]["body"]
        assert len(body["snippet"]["title"]) == 100

    def test_upload_video_with_tags(self, mock_client, tmp_path):
        """Test upload with tags."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "tagged123"})
        mock_service.videos().insert.return_value = mock_request

        tags = ["python", "tutorial", "coding"]

        mock_media_upload = MagicMock()

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload", return_value=mock_media_upload):
                mock_client.upload_video(
                    file_path=str(video_file),
                    title="Test Video",
                    description="Test",
                    tags=tags,
                )

        call_kwargs = mock_service.videos().insert.call_args
        body = call_kwargs[1]["body"]
        assert body["snippet"]["tags"] == tags

    def test_upload_video_http_error(self, mock_client, tmp_path):
        """Test handling of YouTube API HTTP errors."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        mock_service = MagicMock()

        # Create a proper HttpError mock
        mock_http_error = MagicMock()
        mock_http_error.status_code = 403
        mock_http_error.error_details = "Quota exceeded"

        mock_request = MagicMock()
        mock_request.next_chunk.side_effect = Exception("API error")

        mock_service.videos().insert.return_value = mock_request

        mock_media_upload = MagicMock()

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload", return_value=mock_media_upload):
                with pytest.raises(YouTubeUploadError) as exc_info:
                    mock_client.upload_video(
                        file_path=str(video_file),
                        title="Test",
                        description="Test",
                    )

        assert "Failed to upload" in str(exc_info.value)


class TestYouTubeClientUploadFromRequest:
    """Tests for upload_video_from_request method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock YouTube client for testing."""
        with patch("reddit_flow.clients.youtube_client.Path.exists") as mock_exists:
            mock_exists.return_value = True
            client = YouTubeClient()
            return client

    def test_upload_from_request_returns_response(self, mock_client, tmp_path):
        """Test upload_video_from_request returns YouTubeUploadResponse."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        request = YouTubeUploadRequest(
            file_path=str(video_file),
            title="My Video Title",
            description="My description",
            category_id="22",
            privacy_status="public",
        )

        with patch.object(mock_client, "upload_video", return_value="vid123"):
            response = mock_client.upload_video_from_request(request)

        assert isinstance(response, YouTubeUploadResponse)
        assert response.video_id == "vid123"
        assert response.title == "My Video Title"
        assert response.url == "https://www.youtube.com/watch?v=vid123"

    def test_upload_from_request_passes_all_params(self, mock_client, tmp_path):
        """Test that all request parameters are passed to upload_video."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        request = YouTubeUploadRequest(
            file_path=str(video_file),
            title="Title",
            description="Desc",
            category_id="24",
            privacy_status="unlisted",
            made_for_kids=True,
            tags=["tag1", "tag2"],
        )

        with patch.object(mock_client, "upload_video", return_value="vid456") as mock_upload:
            progress_cb = MagicMock()
            mock_client.upload_video_from_request(request, progress_callback=progress_cb)

        mock_upload.assert_called_once_with(
            file_path=str(video_file),
            title="Title",
            description="Desc",
            category_id="24",
            privacy_status="unlisted",
            made_for_kids=True,
            tags=["tag1", "tag2"],
            progress_callback=progress_cb,
        )


class TestYouTubeClientVideoInfo:
    """Tests for get_video_info method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock YouTube client for testing."""
        with patch("reddit_flow.clients.youtube_client.Path.exists") as mock_exists:
            mock_exists.return_value = True
            client = YouTubeClient()
            return client

    def test_get_video_info_success(self, mock_client):
        """Test getting video info successfully."""
        mock_service = MagicMock()
        mock_response = {
            "items": [
                {
                    "id": "vid123",
                    "snippet": {"title": "My Video"},
                    "status": {"privacyStatus": "public"},
                    "statistics": {"viewCount": "100"},
                }
            ]
        }
        mock_service.videos().list().execute.return_value = mock_response

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            info = mock_client.get_video_info("vid123")

        assert info["id"] == "vid123"
        assert info["snippet"]["title"] == "My Video"

    def test_get_video_info_not_found(self, mock_client):
        """Test error when video is not found."""
        mock_service = MagicMock()
        mock_service.videos().list().execute.return_value = {"items": []}

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with pytest.raises(YouTubeUploadError) as exc_info:
                mock_client.get_video_info("nonexistent")

        assert "not found" in str(exc_info.value).lower()


class TestYouTubeClientDeleteVideo:
    """Tests for delete_video method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock YouTube client for testing."""
        with patch("reddit_flow.clients.youtube_client.Path.exists") as mock_exists:
            mock_exists.return_value = True
            client = YouTubeClient()
            return client

    def test_delete_video_success(self, mock_client):
        """Test successful video deletion."""
        mock_service = MagicMock()
        mock_service.videos().delete().execute.return_value = None

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            result = mock_client.delete_video("vid123")

        assert result is True
        mock_service.videos().delete.assert_called_with(id="vid123")

    def test_delete_video_error(self, mock_client):
        """Test error during video deletion."""
        mock_service = MagicMock()
        mock_service.videos().delete().execute.side_effect = Exception("API error")

        with patch.object(mock_client, "_get_authenticated_service", return_value=mock_service):
            with pytest.raises(YouTubeUploadError) as exc_info:
                mock_client.delete_video("vid123")

        assert "Failed to delete" in str(exc_info.value)


class TestYouTubeClientIntegration:
    """Integration-style tests for YouTubeClient."""

    def test_full_upload_workflow(self, tmp_path):
        """Test complete upload workflow with mocked dependencies."""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content" * 1000)

        with patch("reddit_flow.clients.youtube_client.Path.exists") as mock_exists:
            mock_exists.return_value = True

            client = YouTubeClient(
                {
                    "client_secrets_file": "secrets.json",
                    "category_id": "22",
                }
            )

            # Mock the upload
            mock_service = MagicMock()
            mock_request = MagicMock()
            mock_request.next_chunk.return_value = (None, {"id": "workflow123"})
            mock_service.videos().insert.return_value = mock_request

            mock_media_upload = MagicMock()

            with patch.object(client, "_get_authenticated_service", return_value=mock_service):
                with patch("googleapiclient.http.MediaFileUpload", return_value=mock_media_upload):
                    # Create request
                    request = YouTubeUploadRequest(
                        file_path=str(video_file),
                        title="Workflow Test Video",
                        description="Testing the complete workflow",
                        tags=["test", "workflow"],
                    )

                    response = client.upload_video_from_request(request)

            assert response.video_id == "workflow123"
            assert response.title == "Workflow Test Video"
            assert "workflow123" in response.watch_url
            assert "workflow123" in response.studio_url
