"""
Media service for audio and video generation.

This module provides business logic for generating audio via TTS and creating
AI avatar videos from scripts using ElevenLabs and HeyGen APIs.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from reddit_flow.clients import ElevenLabsClient, HeyGenClient
from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import MediaGenerationError, TTSError, VideoGenerationError
from reddit_flow.models import AudioAsset, VideoScript

logger = get_logger(__name__)


@dataclass
class MediaGenerationResult:
    """
    Result of a complete media generation workflow.

    Attributes:
        audio_data: Raw audio bytes from TTS.
        audio_asset: Uploaded audio asset metadata.
        video_id: HeyGen video generation ID.
        video_url: Final video URL (after completion).
    """

    audio_data: bytes
    audio_asset: AudioAsset
    video_id: str
    video_url: Optional[str] = None


class MediaService:
    """
    Service for generating audio and video media from scripts.

    This service orchestrates:
    - Text-to-speech conversion via ElevenLabs
    - Audio upload to HeyGen
    - Avatar video generation via HeyGen
    - Waiting for video completion

    Attributes:
        elevenlabs_client: ElevenLabsClient instance for TTS.
        heygen_client: HeyGenClient instance for video generation.

    Example:
        >>> service = MediaService()
        >>> script = VideoScript(script="Hello world!", title="Test")
        >>> result = await service.generate_video_from_script(script)
        >>> print(result.video_url)
    """

    def __init__(
        self,
        elevenlabs_client: Optional[ElevenLabsClient] = None,
        heygen_client: Optional[HeyGenClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """
        Initialize MediaService.

        Args:
            elevenlabs_client: Optional ElevenLabsClient instance.
            heygen_client: Optional HeyGenClient instance.
            settings: Optional Settings instance.
        """
        self._elevenlabs_client = elevenlabs_client
        self._heygen_client = heygen_client
        self.settings = settings or Settings()
        logger.info("MediaService initialized")

    @property
    def elevenlabs_client(self) -> ElevenLabsClient:
        """Lazy-load ElevenLabs client on first access."""
        if self._elevenlabs_client is None:
            self._elevenlabs_client = ElevenLabsClient()
        return self._elevenlabs_client

    @property
    def heygen_client(self) -> HeyGenClient:
        """Lazy-load HeyGen client on first access."""
        if self._heygen_client is None:
            self._heygen_client = HeyGenClient()
        return self._heygen_client

    def generate_audio(self, text: str) -> bytes:
        """
        Generate audio from text using ElevenLabs TTS.

        Args:
            text: Text to convert to speech.

        Returns:
            Audio data as bytes (MP3 format).

        Raiself.settings.env != "prod":
            logger.info(f"Skipping audio generation in {self.settings.env} mode")
            return b"dummy_audio_bytes"

        if ses:
            TTSError: If audio generation fails.
        """
        if not text or not text.strip():
            raise TTSError("Cannot generate audio from empty text")

        logger.info(f"Generating audio for {len(text)} characters")
        return self.elevenlabs_client.text_to_speech(text)

    def generate_audio_from_script(self, script: VideoScript) -> bytes:
        """
        Generate audio from a VideoScript.

        Args:
            script: VideoScript model with script text.

        Returns:
            Audio data as bytes.

        Raises:
            TTSError: If audio generation fails.
        """
        logger.info(
            f"Generating audio for script: '{script.title[:50]}...' " f"({script.word_count} words)"
        )
        return self.generate_audio(script.script)

    def upload_audio(self, audio_data: bytes) -> AudioAsset:
        """
        Upload audio to HeyGen asset storage.

        Args:
            audio_data: Audio file bytes (MP3/WAV).

        Returns:
            AudioAsset with URL and metadata.

        Raises:
            VideoGenerationError: If upload fails.
        """
        if not audio_data:
            raise VideoGenerationError("Cannot upload empty audio data")

        logger.info(f"Uploading audio: {len(audio_data) / 1024:.2f} KB")
        return self.heygen_client.upload_audio(audio_data)

    def start_video_generation(
        self,
        audio_asset: AudioAsset,
        title: Optional[str] = None,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
    ) -> str:
        """
        Start avatar video generation.

        Args:
            audio_asset: Uploaded audio asset.
            title: Optional video title.
            avatar_id: Override default avatar ID.
            test_mode: Use test mode (watermarked).

        Returns:
            Video ID for tracking generation.

        Raises:
            VideoGenerationError: If video generation fails.
        """
        logger.info(f"Starting video generation: '{title or 'Untitled'}'")

        return self.heygen_client.generate_video(
            audio_url=audio_asset.url,
            title=title,
            avatar_id=avatar_id,
            test_mode=test_mode,
        )

    async def wait_for_video(
        self,
        video_id: str,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Wait for video generation to complete.

        Args:
            video_id: HeyGen video ID.
            update_callback: Optional async callback for status updates.
            timeout: Override default timeout.

        Returns:
            URL of completed video.

        Raises:
            VideoGenerationError: If generation fails or times out.
        """
        logger.info(f"Waiting for video completion: {video_id}")
        return await self.heygen_client.wait_for_video(
            video_id=video_id,
            update_callback=update_callback,
            timeout=timeout,
        )

    async def generate_video_from_script(
        self,
        script: VideoScript,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
        wait_for_completion: bool = True,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> MediaGenerationResult:
        """
        Complete workflow: generate audio and video from a script.

        This method orchestrates the full media generation pipeline:
        1. Convert script text to audio via ElevenLabs
        2. Upload audio to HeyGen
        3. Start video generation
        4. Optionally wait for completion

        Args:
            script: VideoScript with content to convert.
            avatar_id: Override default avatar ID.
            test_mode: Use test mode (watermarked).
            wait_for_completion: Whether to wait for video to complete.
            update_callback: Optional callback for progress updates.
            timeout: Override default wait timeout.

        Returns:
            MediaGenerationResult with all generated assets.

        Raises:
            TTSError: If audio generation fails.
            VideoGenerationError: If video generation fails.
            MediaGenerationError: If overall workflow fails.
        """
        if self.settings.env != "prod":
            logger.info(f"Skipping video generation in {self.settings.env} mode")
            return MediaGenerationResult(
                audio_data=b"dummy_audio",
                audio_asset=AudioAsset(
                    asset_id="test_asset",
                    url="https://example.com/test_audio.mp3",
                ),
                video_id="test_video_id",
                video_url="https://example.com/test_video.mp4",
            )

        try:
            # Step 1: Generate audio from script
            if update_callback:
                await update_callback("Generating audio from script...")

            audio_data = self.generate_audio_from_script(script)

            # Step 2: Upload audio to HeyGen
            if update_callback:
                await update_callback("Uploading audio to HeyGen...")

            audio_asset = self.upload_audio(audio_data)

            # Step 3: Start video generation
            if update_callback:
                await update_callback("Starting video generation...")

            video_id = self.start_video_generation(
                audio_asset=audio_asset,
                title=script.title,
                avatar_id=avatar_id,
                test_mode=test_mode,
            )

            result = MediaGenerationResult(
                audio_data=audio_data,
                audio_asset=audio_asset,
                video_id=video_id,
            )

            # Step 4: Optionally wait for completion
            if wait_for_completion:
                video_url = await self.wait_for_video(
                    video_id=video_id,
                    update_callback=update_callback,
                    timeout=timeout,
                )
                result.video_url = video_url

            logger.info(
                f"Media generation complete: video_id={video_id}, "
                f"completed={result.video_url is not None}"
            )

            return result

        except (TTSError, VideoGenerationError):
            raise
        except Exception as e:
            logger.error(f"Media generation failed: {e}", exc_info=True)
            raise MediaGenerationError(f"Media generation failed: {e}")

    async def generate_video_from_text(
        self,
        text: str,
        title: Optional[str] = None,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
        wait_for_completion: bool = True,
        update_callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[int] = None,
    ) -> MediaGenerationResult:
        """
        Generate video from plain text.

        Convenience method for generating media from raw text instead
        of a VideoScript model.

        Args:
            text: Text content to convert to video.
            title: Optional video title.
            avatar_id: Override default avatar ID.
            test_mode: Use test mode (watermarked).
            wait_for_completion: Whether to wait for video to complete.
            update_callback: Optional callback for progress updates.
            timeout: Override default wait timeout.

        Returns:
            MediaGenerationResult with all generated assets.

        Raises:
            TTSError: If audio generation fails.
            VideoGenerationError: If video generation fails.
        """
        script = VideoScript(
            script=text,
            title=title or "Generated Video",
        )

        return await self.generate_video_from_script(
            script=script,
            avatar_id=avatar_id,
            test_mode=test_mode,
            wait_for_completion=wait_for_completion,
            update_callback=update_callback,
            timeout=timeout,
        )

    def check_video_status(self, video_id: str) -> Dict[str, Any]:
        """
        Check the status of a video generation.

        Args:
            video_id: HeyGen video ID.

        Returns:
            Dictionary with status information.

        Raises:
            VideoGenerationError: If status check fails.
        """
        response = self.heygen_client.check_video_status(video_id)
        return {
            "video_id": response.video_id,
            "status": response.status,
            "video_url": response.video_url,
            "error_message": response.error_message,
        }
