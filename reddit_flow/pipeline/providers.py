"""Built-in provider adapters for script, voice, and video generation."""

from __future__ import annotations

from typing import Any, Optional

from reddit_flow.clients import ElevenLabsClient, GeminiClient, HeyGenClient
from reddit_flow.exceptions import AIGenerationError, TTSError, VideoGenerationError
from reddit_flow.models import AudioAsset, ContentItem, PipelineRequest, RenderProfile
from reddit_flow.pipeline.contracts import ScriptProvider, VideoProvider, VoiceProvider


class _DelegatingScriptProvider(ScriptProvider):
    """Base helper for script providers backed by a client object."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def generate_script(self, content: ContentItem, request: PipelineRequest) -> Any:
        user_opinion = request.user_input
        comments = content.comments

        if not hasattr(self._client, "generate_script"):
            raise AIGenerationError(
                f"{self.provider_name} provider does not implement generate_script"
            )

        return await self._client.generate_script(
            post_text=content.text_content,
            comments_data=comments,
            user_opinion=user_opinion,
            source_post_id=content.source_id,
            source_subreddit=content.source_type,
        )


class GeminiScriptProvider(_DelegatingScriptProvider):
    """Script provider adapter for Google's Gemini models."""

    provider_name = "gemini"

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        super().__init__(client or GeminiClient())


class OpenAIScriptProvider(_DelegatingScriptProvider):
    """An adapter for OpenAI's language models."""

    provider_name = "openai"


class AnthropicScriptProvider(_DelegatingScriptProvider):
    """An adapter for Anthropic's language models."""

    provider_name = "anthropic"


class _DelegatingVoiceProvider(VoiceProvider):
    """Base helper for voice providers backed by a client object."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def generate_audio(self, text: str, request: PipelineRequest) -> bytes:
        if not text.strip():
            raise TTSError("Cannot generate audio from empty text")

        method = None
        for candidate in ("text_to_speech", "generate_audio", "synthesize_speech"):
            if hasattr(self._client, candidate):
                method = getattr(self._client, candidate)
                break

        if method is None:
            raise TTSError(f"{self.provider_name} provider does not implement audio generation")

        return method(text)


class ElevenLabsVoiceProvider(_DelegatingVoiceProvider):
    """Voice provider adapter for ElevenLabs."""

    provider_name = "elevenlabs"

    def __init__(self, client: Optional[ElevenLabsClient] = None) -> None:
        super().__init__(client or ElevenLabsClient())


class OpenAITTSProvider(_DelegatingVoiceProvider):
    """Voice provider adapter for OpenAI's text-to-speech capabilities."""

    provider_name = "openai_tts"


class GoogleCloudTTSProvider(_DelegatingVoiceProvider):
    """Voice provider adapter for Google Cloud Text-to-Speech."""

    provider_name = "google_cloud_tts"


class _DelegatingVideoProvider(VideoProvider):
    """Base helper for video providers backed by a client object."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def start_video_generation(
        self,
        audio_asset: AudioAsset,
        title: Optional[str] = None,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
        render_profile: Optional[RenderProfile] = None,
    ) -> str:
        if hasattr(self._client, "generate_video"):
            return self._client.generate_video(  # type: ignore[no-any-return]
                audio_url=audio_asset.url,
                title=title,
                avatar_id=avatar_id,
                test_mode=test_mode,
            )

        if hasattr(self._client, "start_video_generation"):
            return self._client.start_video_generation(  # type: ignore[no-any-return]
                audio_asset=audio_asset,
                title=title,
                avatar_id=avatar_id,
                test_mode=test_mode,
                render_profile=render_profile,
            )

        raise VideoGenerationError(
            f"{self.provider_name} provider does not implement video generation"
        )

    async def wait_for_video(
        self,
        video_id: str,
        update_callback: Optional[Any] = None,
        timeout: Optional[int] = None,
    ) -> str:
        if not hasattr(self._client, "wait_for_video"):
            raise VideoGenerationError(
                f"{self.provider_name} provider does not implement wait_for_video"
            )

        return await self._client.wait_for_video(  # type: ignore[no-any-return]
            video_id=video_id,
            update_callback=update_callback,
            timeout=timeout,
        )


class HeyGenVideoProvider(_DelegatingVideoProvider):
    """Video provider adapter for HeyGen."""

    provider_name = "heygen"

    def __init__(self, client: Optional[HeyGenClient] = None) -> None:
        super().__init__(client or HeyGenClient())


class TavusVideoProvider(_DelegatingVideoProvider):
    """Video provider adapter for Tavus."""

    provider_name = "tavus"


__all__ = [
    "GeminiScriptProvider",
    "OpenAIScriptProvider",
    "AnthropicScriptProvider",
    "ElevenLabsVoiceProvider",
    "OpenAITTSProvider",
    "GoogleCloudTTSProvider",
    "HeyGenVideoProvider",
    "TavusVideoProvider",
]
