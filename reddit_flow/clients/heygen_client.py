"""
HeyGen API client.

This module provides the client for AI avatar video generation using
the HeyGen API v2.
"""

import asyncio
import os
import time
from typing import Any, Callable, Dict, Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from reddit_flow.clients.base import BaseClient, HTTPClientMixin
from reddit_flow.config import get_logger
from reddit_flow.exceptions import ConfigurationError, VideoGenerationError
from reddit_flow.models import AudioAsset, VideoGenerationRequest, VideoGenerationResponse

logger = get_logger(__name__)


class HeyGenClient(BaseClient, HTTPClientMixin):
    """
    Client for HeyGen avatar video generation (API v2).

    This client handles:
    - Uploading audio assets to HeyGen
    - Starting video generation with AI avatars
    - Polling for video completion status

    Attributes:
        service_name: Name of the service for logging/identification.
        base_url: The HeyGen API base URL.
        upload_url: The HeyGen asset upload URL.

    Example:
        >>> client = HeyGenClient(config={
        ...     "api_key": "your-key",
        ...     "avatar_id": "your-avatar-id"
        ... })
        >>> audio_url = client.upload_audio(audio_bytes)
        >>> video_id = client.generate_video(audio_url, title="My Video")
        >>> video_url = await client.wait_for_video(video_id)
    """

    service_name = "HeyGen"

    # API configuration
    DEFAULT_BASE_URL = "https://api.heygen.com"
    DEFAULT_UPLOAD_URL = "https://upload.heygen.com/v1/asset"
    DEFAULT_VIDEO_WIDTH = 1080
    DEFAULT_VIDEO_HEIGHT = 1920
    DEFAULT_WAIT_TIMEOUT = 600  # 10 minutes
    DEFAULT_UPLOAD_TIMEOUT = 120
    DEFAULT_REQUEST_TIMEOUT = 60

    def _initialize(self) -> None:
        """
        Initialize the HeyGen client.

        Loads API key and avatar ID from config or environment variables.

        Raises:
            ConfigurationError: If API key or avatar ID is missing.
        """
        # Get API key from config or environment
        self._api_key = self._config.get("api_key") or os.getenv("HEYGEN_API_KEY")
        self._avatar_id = self._config.get("avatar_id") or os.getenv("HEYGEN_AVATAR_ID")

        if not self._api_key:
            raise ConfigurationError(
                "HeyGen API key not found",
                details={"required": "HEYGEN_API_KEY environment variable or api_key in config"},
            )

        if not self._avatar_id:
            raise ConfigurationError(
                "HeyGen avatar ID not found",
                details={
                    "required": "HEYGEN_AVATAR_ID environment variable or avatar_id in config"
                },
            )

        # Get optional settings
        self._base_url = self._config.get("base_url", self.DEFAULT_BASE_URL)
        self._upload_url = self._config.get("upload_url", self.DEFAULT_UPLOAD_URL)
        self._video_width = self._config.get("video_width", self.DEFAULT_VIDEO_WIDTH)
        self._video_height = self._config.get("video_height", self.DEFAULT_VIDEO_HEIGHT)
        self._wait_timeout = self._config.get("wait_timeout", self.DEFAULT_WAIT_TIMEOUT)
        self._test_mode = self._config.get("test_mode", False)

        logger.info(
            "HeyGen client initialized",
            extra={
                "avatar_id": self._avatar_id[:8] + "...",
                "dimensions": f"{self._video_width}x{self._video_height}",
            },
        )

    def _health_check(self) -> bool:
        """
        Verify the HeyGen API is accessible.

        Checks the remaining quota endpoint to verify credentials.

        Returns:
            True if the API is accessible and credentials are valid.
        """
        try:
            url = f"{self._base_url}/v1/video.remaining_quota"
            headers = self._get_auth_headers()
            response = requests.get(url, headers=headers, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"HeyGen health check failed: {e}")
            return False

    @property
    def avatar_id(self) -> str:
        """Get the configured avatar ID."""
        return self._avatar_id  # type: ignore[return-value]

    @property
    def base_url(self) -> str:  # type: ignore[override]
        """Get the API base URL."""
        return self._base_url  # type: ignore[return-value]

    @property
    def video_dimensions(self) -> tuple:
        """Get the configured video dimensions."""
        return (self._video_width, self._video_height)

    def _get_auth_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Get headers with API key authentication.

        Args:
            extra: Optional additional headers to include.

        Returns:
            Dictionary of headers including API key.
        """
        headers: dict[str, str] = {
            "X-Api-Key": str(self._api_key),
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def upload_audio(self, audio_data: bytes, content_type: str = "audio/mpeg") -> AudioAsset:
        """
        Upload audio to HeyGen asset storage.

        Args:
            audio_data: Audio file bytes (MP3/WAV).
            content_type: MIME type of the audio (default: audio/mpeg).

        Returns:
            AudioAsset model with URL and metadata.

        Raises:
            VideoGenerationError: If upload fails.

        Example:
            >>> asset = client.upload_audio(audio_bytes)
            >>> print(asset.url)
        """
        try:
            headers = {
                "X-API-KEY": self._api_key,
                "Content-Type": content_type,
            }

            logger.debug(f"Uploading {len(audio_data) / 1024:.2f} KB audio to HeyGen")

            response = requests.post(
                self._upload_url,
                data=audio_data,
                headers=headers,
                timeout=self.DEFAULT_UPLOAD_TIMEOUT,
            )
            response.raise_for_status()

            result = response.json()
            audio_url = result["data"]["url"]
            asset_id = result["data"].get("id")

            logger.info(f"Audio uploaded successfully: {audio_url[:50]}...")

            return AudioAsset(
                url=audio_url,
                asset_id=asset_id,
                file_size_bytes=len(audio_data),
            )

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            response_text = e.response.text if e.response else str(e)
            logger.error(f"HeyGen upload error: {status_code} - {response_text}")
            raise VideoGenerationError(
                f"Audio upload failed: {e}",
                status_code=status_code,
                response_body=response_text,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error uploading audio: {e}")
            raise VideoGenerationError(f"Network error during audio upload: {e}")
        except Exception as e:
            logger.error(f"Error uploading audio: {e}", exc_info=True)
            raise VideoGenerationError(f"Failed to upload audio: {e}")

    def upload_audio_url(self, audio_data: bytes, content_type: str = "audio/mpeg") -> str:
        """
        Upload audio and return just the URL (backward-compatible).

        Args:
            audio_data: Audio file bytes (MP3/WAV).
            content_type: MIME type of the audio.

        Returns:
            URL of uploaded audio asset.

        Raises:
            VideoGenerationError: If upload fails.
        """
        asset = self.upload_audio(audio_data, content_type)
        return asset.url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def generate_video(
        self,
        audio_url: str,
        title: Optional[str] = None,
        avatar_id: Optional[str] = None,
        avatar_style: str = "normal",
        test_mode: Optional[bool] = None,
        enable_captions: bool = True,
    ) -> str:
        """
        Start avatar video generation using HeyGen API v2.

        Args:
            audio_url: URL of uploaded audio (from upload_audio).
            title: Optional title for the video.
            avatar_id: Override the default avatar ID.
            avatar_style: Avatar style (normal, circle, etc.).
            test_mode: Override test mode setting.
            enable_captions: Whether to generate captions.

        Returns:
            Video ID for tracking generation.

        Raises:
            VideoGenerationError: If video generation request fails.

        Example:
            >>> video_id = client.generate_video(audio_url, title="My Video")
        """
        try:
            url = f"{self._base_url}/v2/video/generate"
            headers = {
                "x-api-key": self._api_key,
                "content-type": "application/json",
            }

            # Use provided values or defaults
            use_avatar = avatar_id or self._avatar_id
            use_test_mode = test_mode if test_mode is not None else self._test_mode

            data: Dict[str, Any] = {
                "video_inputs": [
                    {
                        "character": {
                            "type": "avatar",
                            "avatar_id": use_avatar,
                            "avatar_style": avatar_style,
                        },
                        "voice": {
                            "type": "audio",
                            "audio_url": audio_url,
                        },
                    }
                ],
                "test": use_test_mode,
                "caption": enable_captions,
                "dimension": {
                    "width": self._video_width,
                    "height": self._video_height,
                },
            }

            if title:
                data["title"] = title

            logger.debug("Requesting HeyGen video generation (v2)")
            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=self.DEFAULT_REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            video_id = response.json()["data"]["video_id"]
            logger.info(f"Video generation started: {video_id}")
            return video_id

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            response_text = e.response.text if e.response else str(e)
            logger.error(f"HeyGen generation error: {status_code} - {response_text}")
            raise VideoGenerationError(
                f"Video generation failed: {e}",
                status_code=status_code,
                response_body=response_text,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error generating video: {e}")
            raise VideoGenerationError(f"Network error during video generation: {e}")
        except Exception as e:
            logger.error(f"Error generating video: {e}", exc_info=True)
            raise VideoGenerationError(f"Failed to start video generation: {e}")

    def generate_video_from_request(self, request: VideoGenerationRequest) -> str:
        """
        Start video generation from a VideoGenerationRequest model.

        Args:
            request: VideoGenerationRequest with all parameters.

        Returns:
            Video ID for tracking generation.

        Raises:
            VideoGenerationError: If video generation request fails.
        """
        return self.generate_video(
            audio_url=request.audio_url,
            title=request.title,
            avatar_id=request.avatar_id,
            avatar_style=request.avatar_style,
            test_mode=request.test_mode,
            enable_captions=request.enable_captions,
        )

    def check_video_status(self, video_id: str) -> VideoGenerationResponse:
        """
        Check the status of a video generation.

        Args:
            video_id: HeyGen video ID.

        Returns:
            VideoGenerationResponse with current status.

        Raises:
            VideoGenerationError: If status check fails.
        """
        try:
            url = f"{self._base_url}/v1/video_status.get"
            headers = self._get_auth_headers()

            response = requests.get(
                url,
                params={"video_id": video_id},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()["data"]

            return VideoGenerationResponse(
                video_id=video_id,
                status=data["status"],
                video_url=data.get("video_url"),
                error_message=data.get("error"),
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"Error checking video status: {e}")
            raise VideoGenerationError(f"Failed to check video status: {e}")
        except Exception as e:
            logger.error(f"Error checking video status: {e}")
            raise VideoGenerationError(f"Failed to check video status: {e}")

    async def wait_for_video(
        self,
        video_id: str,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Wait for video generation to complete with timeout.

        Args:
            video_id: HeyGen video ID.
            update_callback: Optional async callback for status updates.
            timeout: Override default wait timeout.

        Returns:
            URL of completed video.

        Raises:
            VideoGenerationError: If generation fails or times out.

        Example:
            >>> video_url = await client.wait_for_video(video_id)
        """
        url = f"{self._base_url}/v1/video_status.get"
        headers = self._get_auth_headers()

        start_time = time.time()
        attempt = 0
        wait_time: float = 10
        max_wait_time: float = 60
        use_timeout = timeout or self._wait_timeout

        try:
            while True:
                elapsed = time.time() - start_time

                if elapsed > use_timeout:
                    raise VideoGenerationError(
                        f"Video generation timed out after {use_timeout} seconds"
                    )

                attempt += 1
                logger.debug(f"Checking video status (attempt {attempt}, elapsed: {elapsed:.0f}s)")

                # Run blocking request in a thread
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    params={"video_id": video_id},
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()

                data = response.json()["data"]
                status = data["status"]

                if status == "completed":
                    video_url = data["video_url"]
                    logger.info(f"Video completed after {elapsed:.0f}s: {video_url[:50]}...")
                    return video_url

                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    logger.error(f"HeyGen video generation failed: {error}")
                    raise VideoGenerationError(f"Video generation failed: {error}")

                if update_callback:
                    await update_callback(f"Video generation: {status} ({elapsed:.0f}s elapsed)")

                logger.info(f"Video status: {status}, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)

                wait_time = min(wait_time * 1.5, max_wait_time)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking video status: {e}", exc_info=True)
            raise VideoGenerationError(f"Failed to check video status: {e}")

    def get_remaining_quota(self) -> Dict[str, Any]:
        """
        Get remaining video generation quota.

        Returns:
            Dictionary with quota information.

        Raises:
            VideoGenerationError: If API call fails.
        """
        try:
            url = f"{self._base_url}/v1/video.remaining_quota"
            headers = self._get_auth_headers()
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get("data", {})
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to get quota: {e}")
            raise VideoGenerationError(f"Failed to get quota: {e}")
        except Exception as e:
            logger.error(f"Error getting quota: {e}")
            raise VideoGenerationError(f"Error getting quota: {e}")
