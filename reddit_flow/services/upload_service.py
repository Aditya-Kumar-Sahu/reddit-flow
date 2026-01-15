"""
Upload service for YouTube publishing.

This module provides business logic for uploading videos to YouTube,
including title/description formatting and metadata management.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from reddit_flow.clients import YouTubeClient
from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import YouTubeUploadError
from reddit_flow.models import VideoScript, YouTubeUploadRequest, YouTubeUploadResponse

logger = get_logger(__name__)


@dataclass
class UploadResult:
    """
    Result of a complete upload workflow.

    Attributes:
        video_id: YouTube video ID.
        title: Uploaded video title.
        url: YouTube watch URL.
        studio_url: YouTube Studio edit URL.
        local_file_path: Path to local video file (if downloaded).
    """

    video_id: str
    title: str
    url: str
    studio_url: str
    local_file_path: Optional[str] = None


class UploadService:
    """
    Service for uploading videos to YouTube.

    This service handles:
    - Downloading videos from URLs to local files
    - Formatting titles and descriptions for YouTube
    - Uploading videos with metadata
    - Managing upload progress callbacks

    Attributes:
        youtube_client: YouTubeClient instance for API calls.
        default_category_id: Default YouTube category ID.

    Example:
        >>> service = UploadService()
        >>> script = VideoScript(script="...", title="My Video")
        >>> result = service.upload_from_url(
        ...     video_url="https://example.com/video.mp4",
        ...     script=script
        ... )
        >>> print(result.url)
    """

    # YouTube video limits
    MAX_TITLE_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 5000

    def __init__(
        self,
        youtube_client: Optional[YouTubeClient] = None,
        default_category_id: str = "22",
        default_privacy: str = "public",
        settings: Optional[Settings] = None,
    ) -> None:
        """
        Initialize UploadService.

        Args:
            youtube_client: Optional YouTubeClient instance.
            default_category_id: Default YouTube category (22 = People & Blogs).
            default_privacy: Default privacy status (public, private, unlisted).
            settings: Optional Settings instance.
        """
        self._youtube_client = youtube_client
        self._default_category_id = default_category_id
        self._default_privacy = default_privacy
        self.settings = settings or Settings()
        logger.info(
            f"UploadService initialized (category={default_category_id}, "
            f"privacy={default_privacy})"
        )

    @property
    def youtube_client(self) -> YouTubeClient:
        """Lazy-load YouTube client on first access."""
        if self._youtube_client is None:
            self._youtube_client = YouTubeClient()
        return self._youtube_client

    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str = "",
        category_id: Optional[str] = None,
        privacy_status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        made_for_kids: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> YouTubeUploadResponse:
        """
        Upload a local video file to YouTube.

        Args:
            file_path: Path to local video file.
            title: Video title (will be truncated to 100 chars).
            description: Video description (will be truncated to 5000 chars).
            category_id: YouTube category ID (defaults to service default).
            privacy_status: Privacy setting (defaults to service default).
            tags: Optional list of video tags.
            made_for_kids: Whether video is made for kids.
            progress_callback: Optional callback for upload progress (0-100).

        Returns:
            YouTubeUploadResponse with video details.

        Raises:
            YouTubeUploadError: If upload fails.
        """
        if self.settings.env != "prod":
            logger.info(f"Skipping YouTube upload in {self.settings.env} mode")
            return YouTubeUploadResponse(
                video_id="test_video_id",
                title=title,
                url="https://youtube.com/watch?v=test_video_id",
            )

        # Validate file exists
        video_path = Path(file_path)
        if not video_path.exists():
            raise YouTubeUploadError(f"Video file not found: {file_path}")

        # Format title and description
        formatted_title = self._format_title(title)
        formatted_description = self._format_description(description)

        logger.info(
            f"Uploading video: '{formatted_title}' "
            f"({video_path.stat().st_size / (1024*1024):.2f} MB)"
        )

        # Create upload request
        request = YouTubeUploadRequest(
            file_path=str(video_path),
            title=formatted_title,
            description=formatted_description,
            category_id=category_id or self._default_category_id,
            privacy_status=privacy_status or self._default_privacy,
            tags=tags or [],
            made_for_kids=made_for_kids,
        )

        # Perform upload
        response = self.youtube_client.upload_video_from_request(
            request=request,
            progress_callback=progress_callback,
        )

        logger.info(f"Video uploaded: {response.video_id} - {response.watch_url}")
        return response

    def upload_from_script(
        self,
        file_path: str,
        script: VideoScript,
        additional_description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> YouTubeUploadResponse:
        """
        Upload a video using metadata from a VideoScript.

        Formats the title and description using the script's content
        and metadata.

        Args:
            file_path: Path to local video file.
            script: VideoScript with title and metadata.
            additional_description: Extra text to append to description.
            tags: Optional list of video tags.
            privacy_status: Override default privacy status.
            progress_callback: Optional callback for upload progress.

        Returns:
            YouTubeUploadResponse with video details.

        Raises:
            YouTubeUploadError: If upload fails.
        """
        # Build description from script metadata
        description = self._build_description_from_script(script, additional_description)

        # Use youtube_title if available, otherwise regular title
        title = script.youtube_title or script.title

        return self.upload_video(
            file_path=file_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            progress_callback=progress_callback,
        )

    def upload_from_url(
        self,
        video_url: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: Optional[str] = None,
        keep_local_file: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> UploadResult:
        """
        Download video from URL and upload to YouTube.

        Downloads the video to a temporary file, uploads it to YouTube,
        and optionally keeps the local file.

        Args:
            video_url: URL of video to download.
            title: Video title.
            description: Video description.
            tags: Optional list of video tags.
            privacy_status: Override default privacy status.
            keep_local_file: Whether to keep the downloaded file.
            progress_callback: Optional callback for upload progress.

        Returns:
            UploadResult with video details and optional local path.

        Raises:
            YouTubeUploadError: If download or upload fails.
        """
        # Skip download/upload in non-prod environments
        if self.settings.env != "prod":
            logger.info(f"Skipping video download/upload in {self.settings.env} mode")
            return UploadResult(
                video_id="test_video_id",
                title=title,
                url="https://youtube.com/watch?v=test_video_id",
                studio_url="https://studio.youtube.com/video/test_video_id/edit",
                local_file_path=None,
            )

        # Download video to temporary file
        local_path = self._download_video(video_url)

        try:
            # Upload to YouTube
            response = self.upload_video(
                file_path=local_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy_status,
                progress_callback=progress_callback,
            )

            result = UploadResult(
                video_id=response.video_id,
                title=response.title,
                url=response.watch_url,
                studio_url=response.studio_url,
                local_file_path=local_path if keep_local_file else None,
            )

            # Clean up temporary file if not keeping
            if not keep_local_file:
                self._cleanup_file(local_path)

            return result

        except Exception:
            # Clean up on error
            self._cleanup_file(local_path)
            raise

    def upload_from_url_with_script(
        self,
        video_url: str,
        script: VideoScript,
        additional_description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: Optional[str] = None,
        keep_local_file: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> UploadResult:
        """
        Download video from URL and upload using script metadata.

        Combines URL download with script-based metadata formatting.

        Args:
            video_url: URL of video to download.
            script: VideoScript with title and metadata.
            additional_description: Extra text for description.
            tags: Optional list of video tags.
            privacy_status: Override default privacy status.
            keep_local_file: Whether to keep the downloaded file.
            progress_callback: Optional callback for upload progress.

        Returns:
            UploadResult with video details.

        Raises:
            YouTubeUploadError: If download or upload fails.
        """
        # Build description and get title
        description = self._build_description_from_script(script, additional_description)
        title = script.youtube_title or script.title

        return self.upload_from_url(
            video_url=video_url,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            keep_local_file=keep_local_file,
            progress_callback=progress_callback,
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
        return self.youtube_client.get_video_info(video_id)

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
        return self.youtube_client.delete_video(video_id)

    def _format_title(self, title: str) -> str:
        """
        Format title for YouTube.

        Truncates to max length with ellipsis if needed.

        Args:
            title: Original title.

        Returns:
            Formatted title within YouTube limits.
        """
        if not title:
            return "Untitled Video"

        title = title.strip()
        if len(title) > self.MAX_TITLE_LENGTH:
            return title[: self.MAX_TITLE_LENGTH - 3] + "..."
        return title

    def _format_description(self, description: str) -> str:
        """
        Format description for YouTube.

        Truncates to max length if needed.

        Args:
            description: Original description.

        Returns:
            Formatted description within YouTube limits.
        """
        if not description:
            return ""

        description = description.strip()
        if len(description) > self.MAX_DESCRIPTION_LENGTH:
            return description[: self.MAX_DESCRIPTION_LENGTH - 3] + "..."
        return description

    def _build_description_from_script(
        self,
        script: VideoScript,
        additional_text: str = "",
    ) -> str:
        """
        Build a YouTube description from a VideoScript.

        Args:
            script: VideoScript with metadata.
            additional_text: Extra text to append.

        Returns:
            Formatted description string.
        """
        parts = []

        # Add source info if available
        if script.source_subreddit:
            source_line = f"📍 Source: r/{script.source_subreddit}"
            if script.source_post_id:
                source_line += f" (Post: {script.source_post_id})"
            parts.append(source_line)

        # Add script summary (first 500 chars)
        if script.script:
            summary = script.script[:500]
            if len(script.script) > 500:
                summary += "..."
            parts.append(f"\n{summary}")

        # Add user opinion if available
        if script.user_opinion:
            parts.append(f"\n💬 Commentary: {script.user_opinion[:200]}")

        # Add additional text
        if additional_text:
            parts.append(f"\n{additional_text}")

        # Add generated info
        parts.append("\n\n---")
        parts.append("🤖 Generated with AI assistance")

        description = "\n".join(parts)
        return self._format_description(description)

    def _download_video(self, video_url: str) -> str:
        """
        Download video from URL to temporary file.

        Args:
            video_url: URL of video to download.

        Returns:
            Path to downloaded temporary file.

        Raises:
            YouTubeUploadError: If download fails.
        """
        try:
            logger.info(f"Downloading video from: {video_url[:50]}...")

            response = requests.get(video_url, stream=True, timeout=300)
            response.raise_for_status()

            # Create temp file with .mp4 extension
            fd, temp_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)

            # Write video content
            total_size = 0
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total_size += len(chunk)

            logger.info(f"Video downloaded: {total_size / (1024*1024):.2f} MB to {temp_path}")
            return temp_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download video: {e}")
            raise YouTubeUploadError(f"Failed to download video from URL: {e}")
        except Exception as e:
            logger.error(f"Error downloading video: {e}", exc_info=True)
            raise YouTubeUploadError(f"Video download failed: {e}")

    def _cleanup_file(self, file_path: str) -> None:
        """
        Clean up a temporary file.

        Args:
            file_path: Path to file to delete.
        """
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up file {file_path}: {e}")
