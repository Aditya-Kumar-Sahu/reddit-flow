"""
YouTube Data API client.

This module provides the client for video uploads to YouTube using
the YouTube Data API v3 with OAuth2 authentication.
"""

import os
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, Optional

from reddit_flow.clients.base import BaseClient
from reddit_flow.config import get_logger
from reddit_flow.exceptions import YouTubeUploadError
from reddit_flow.models import YouTubeUploadRequest, YouTubeUploadResponse

logger = get_logger(__name__)


class YouTubeClient(BaseClient):
    """
    Client for YouTube video uploads.

    This client handles OAuth2 authentication and video uploads to YouTube
    using the YouTube Data API v3.

    Attributes:
        service_name: Identifies this as the YouTube client.
        scopes: OAuth2 scopes required for upload.

    Configuration Options:
        client_secrets_file: Path to OAuth2 client secrets JSON file.
        token_file: Path to store/load OAuth2 tokens (default: "token.json").
        category_id: Default YouTube category ID (default: "22" = People & Blogs).
        chunk_size: Upload chunk size in bytes (default: 1MB).

    Environment Variables:
        YOUTUBE_CLIENT_SECRETS_FILE: Path to client secrets file.
        YOUTUBE_CATEGORY_ID: Default category ID.

    Example:
        >>> client = YouTubeClient({
        ...     "client_secrets_file": "youtube-client.json",
        ...     "category_id": "22"
        ... })
        >>> video_id = client.upload_video(
        ...     file_path="video.mp4",
        ...     title="My Video",
        ...     description="Video description"
        ... )
    """

    service_name: ClassVar[str] = "YouTube"

    # OAuth2 scopes for YouTube upload
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def _initialize(self) -> None:
        """
        Initialize YouTube client with OAuth2 configuration.

        Loads client secrets file path and prepares for authentication.
        Actual authentication is deferred until first API call.

        Raises:
            ConfigurationError: If client secrets file is not configured.
        """
        # Get client secrets file path
        self._client_secrets_file = self._config.get(
            "client_secrets_file",
            os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "youtube-client.json"),
        )
        self._secrets_path = Path(self._client_secrets_file)

        # Token storage path
        self._token_file = self._config.get("token_file", "token.json")
        self._token_path = Path(self._token_file)

        # Default category ID
        self._category_id = self._config.get(
            "category_id",
            os.environ.get("YOUTUBE_CATEGORY_ID", "22"),
        )

        # Upload settings
        self._chunk_size = self._config.get("chunk_size", 1024 * 1024)  # 1MB default

        # Service instance (lazy loaded)
        self._service = None

        # Optional progress callback
        self._progress_callback: Optional[Callable[[int], None]] = None

        logger.debug(f"YouTube client configured with secrets: {self._client_secrets_file}")

    def _health_check(self) -> bool:
        """
        Verify YouTube API access by checking authentication.

        Returns:
            True if authentication is valid or can be refreshed.

        Raises:
            YouTubeUploadError: If authentication fails.
        """
        try:
            # Attempt to get authenticated service
            self._get_authenticated_service()
            return True
        except Exception as e:
            logger.error(f"YouTube health check failed: {e}")
            return False

    def _get_authenticated_service(self) -> Any:
        """
        Get authenticated YouTube service.

        This method handles OAuth2 authentication flow:
        1. Load existing token if available
        2. Refresh expired token if possible
        3. Run OAuth flow for new authentication

        Returns:
            Authenticated YouTube API service object.

        Raises:
            YouTubeUploadError: If authentication fails.
        """
        if self._service:
            return self._service

        try:
            # Import Google libraries here to avoid import errors if not installed
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            if not self._secrets_path.exists():
                raise YouTubeUploadError(
                    f"YouTube client secrets file not found: {self._secrets_path}\n"
                    "Please download it from Google Cloud Console"
                )

            creds = None

            # Load existing token
            if self._token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self._token_path), self.SCOPES)

            # Refresh or obtain new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing YouTube credentials")
                    creds.refresh(Request())
                else:
                    logger.info("Starting YouTube OAuth flow")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self._secrets_path), self.SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                # Save credentials for next run
                with open(self._token_path, "w") as token:
                    token.write(creds.to_json())
                logger.info("YouTube credentials saved")

            self._service = build("youtube", "v3", credentials=creds)
            logger.info("YouTube service authenticated")
            return self._service

        except YouTubeUploadError:
            raise
        except Exception as e:
            logger.error(f"YouTube authentication failed: {e}", exc_info=True)
            raise YouTubeUploadError(f"Failed to authenticate with YouTube: {e}")

    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str = "",
        category_id: Optional[str] = None,
        privacy_status: str = "public",
        made_for_kids: bool = False,
        tags: Optional[list[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Upload video to YouTube.

        Args:
            file_path: Path to video file.
            title: Video title (max 100 chars, will be truncated).
            description: Video description (max 5000 chars).
            category_id: YouTube category ID (defaults to config value).
            privacy_status: Privacy setting ("public", "private", "unlisted").
            made_for_kids: Whether video is made for kids.
            tags: Optional list of video tags.
            progress_callback: Optional callback for upload progress (0-100).

        Returns:
            YouTube video ID.

        Raises:
            YouTubeUploadError: If upload fails.
        """
        try:
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaFileUpload

            service = self._get_authenticated_service()

            # Validate file exists
            video_path = Path(file_path)
            if not video_path.exists():
                raise YouTubeUploadError(f"Video file not found: {file_path}")

            file_size = video_path.stat().st_size
            logger.info(f"Uploading video: {file_size / (1024*1024):.2f} MB")

            # Build request body
            body = {
                "snippet": {
                    "title": title[:100],  # YouTube limit
                    "description": description[:5000],  # YouTube limit
                    "categoryId": category_id or self._category_id,
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": made_for_kids,
                },
            }

            if tags:
                body["snippet"]["tags"] = tags

            # Create media upload
            media = MediaFileUpload(
                str(video_path),
                chunksize=self._chunk_size,
                resumable=True,
            )

            # Execute upload request
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            last_progress = 0

            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress - last_progress >= 10:  # Log every 10%
                        logger.info(f"Upload progress: {progress}%")
                        last_progress = progress
                        if progress_callback:
                            progress_callback(progress)

            video_id = response["id"]
            logger.info(f"Video uploaded successfully: {video_id}")
            return video_id

        except YouTubeUploadError:
            raise
        except HttpError as e:
            logger.error(f"YouTube API error: {e.status_code} - {e.error_details}")
            raise YouTubeUploadError(f"YouTube upload failed: {e}")
        except Exception as e:
            logger.error(f"Error uploading to YouTube: {e}", exc_info=True)
            raise YouTubeUploadError(f"Failed to upload video: {e}")

    def upload_video_from_request(
        self,
        request: YouTubeUploadRequest,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> YouTubeUploadResponse:
        """
        Upload video using a YouTubeUploadRequest model.

        This method provides a more structured interface using Pydantic models.

        Args:
            request: YouTubeUploadRequest with all upload parameters.
            progress_callback: Optional callback for upload progress (0-100).

        Returns:
            YouTubeUploadResponse with video details.

        Raises:
            YouTubeUploadError: If upload fails.
        """
        video_id = self.upload_video(
            file_path=request.file_path,
            title=request.title,
            description=request.description,
            category_id=request.category_id,
            privacy_status=request.privacy_status,
            made_for_kids=request.made_for_kids,
            tags=request.tags,
            progress_callback=progress_callback,
        )

        return YouTubeUploadResponse(
            video_id=video_id,
            title=request.title,
            url=f"https://www.youtube.com/watch?v={video_id}",
        )

    def get_video_info(self, video_id: str) -> Dict[str, Any]:
        """
        Get information about an uploaded video.

        Args:
            video_id: YouTube video ID.

        Returns:
            Dictionary with video information.

        Raises:
            YouTubeUploadError: If request fails.
        """
        try:
            service = self._get_authenticated_service()

            response = (
                service.videos().list(part="snippet,status,statistics", id=video_id).execute()
            )

            if not response.get("items"):
                raise YouTubeUploadError(f"Video not found: {video_id}")

            return response["items"][0]

        except YouTubeUploadError:
            raise
        except Exception as e:
            logger.error(f"Error getting video info: {e}", exc_info=True)
            raise YouTubeUploadError(f"Failed to get video info: {e}")

    def delete_video(self, video_id: str) -> bool:
        """
        Delete a video from YouTube.

        Args:
            video_id: YouTube video ID to delete.

        Returns:
            True if deletion was successful.

        Raises:
            YouTubeUploadError: If deletion fails.
        """
        try:
            service = self._get_authenticated_service()
            service.videos().delete(id=video_id).execute()
            logger.info(f"Video deleted: {video_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting video: {e}", exc_info=True)
            raise YouTubeUploadError(f"Failed to delete video: {e}")
