"""Phase 3 tests for provider abstraction and target-specific briefs."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from reddit_flow.models import AudioAsset, ContentItem, VideoScript
from reddit_flow.pipeline.registry import ProviderRegistry
from reddit_flow.services.media_service import MediaService
from reddit_flow.services.script_service import ScriptService


class DummyScriptProvider:
    """Minimal script provider used to verify registry resolution."""

    def __init__(self, name: str, result: VideoScript) -> None:
        self.provider_name = name
        self.result = result
        self.calls = []

    async def generate_script(self, content, request):
        self.calls.append((content, request))
        return self.result


class DummyVoiceProvider:
    """Minimal voice provider used to verify registry resolution."""

    def __init__(self, name: str, result: bytes) -> None:
        self.provider_name = name
        self.result = result
        self.calls = []

    def generate_audio(self, text, request):
        self.calls.append((text, request))
        return self.result


class DummyVideoProvider:
    """Minimal video provider used to verify registry resolution."""

    def __init__(self, name: str, video_id: str, video_url: str) -> None:
        self.provider_name = name
        self.video_id = video_id
        self.video_url = video_url
        self.calls = []
        self.wait_calls = []

    def start_video_generation(
        self, audio_asset, title=None, avatar_id=None, test_mode=False, render_profile=None
    ):
        self.calls.append(
            {
                "audio_asset": audio_asset,
                "title": title,
                "avatar_id": avatar_id,
                "test_mode": test_mode,
                "render_profile": render_profile,
            }
        )
        return self.video_id

    async def wait_for_video(self, video_id, update_callback=None, timeout=None):
        self.wait_calls.append(
            {
                "video_id": video_id,
                "update_callback": update_callback,
                "timeout": timeout,
            }
        )
        return self.video_url


@pytest.fixture
def sample_content_item():
    """Create canonical content for provider tests."""
    return ContentItem(
        source_type="medium_article",
        source_id="story-123",
        source_url="https://medium.com/@writer/story-123",
        title="A Medium Story",
        body="A short article body that can be turned into a script.",
        comments=[{"body": "Useful", "author": "reader1", "score": 10}],
    )


@pytest.fixture
def sample_video_script():
    """Create a sample script for media provider tests."""
    return VideoScript(script="A polished narration script.", title="Provider Test")


class TestScriptBriefs:
    """Tests for target-specific script briefs."""

    def test_build_script_brief_for_instagram_reel(self, mock_prod_settings, sample_content_item):
        """Instagram briefs should bias toward short, vertical, hook-first scripts."""
        service = ScriptService(settings=mock_prod_settings)

        brief = service.build_script_brief(sample_content_item, target="instagram_reel")

        assert brief.target == "instagram_reel"
        assert brief.max_words <= 180
        assert brief.hook_required is True
        assert brief.aspect_ratio == "9:16"
        assert brief.caption_style == "short"

    def test_build_script_brief_for_messaging_summary(
        self, mock_prod_settings, sample_content_item
    ):
        """Messaging briefs should be concise and CTA-light."""
        service = ScriptService(settings=mock_prod_settings)

        brief = service.build_script_brief(sample_content_item, target="messaging_summary")

        assert brief.target == "messaging_summary"
        assert brief.max_words <= 120
        assert brief.cta_required is False
        assert brief.caption_style == "summary"


class TestScriptProviderSelection:
    """Tests for script provider fallback resolution."""

    @pytest.mark.asyncio
    async def test_generate_script_from_content_item_uses_fallback_provider_order(
        self, mock_prod_settings, sample_content_item
    ):
        """The service should resolve the first available provider from the fallback chain."""
        fallback = DummyScriptProvider(
            "openai",
            VideoScript(script="OpenAI result", title="OpenAI title"),
        )

        registry = ProviderRegistry(provider_kind="script")
        registry.register("openai", fallback)

        settings = SimpleNamespace(
            env="prod",
            default_script_provider="anthropic",
            script_provider_fallbacks=["openai"],
            enable_provider_fallbacks=True,
        )

        service = ScriptService(
            settings=settings,
            script_provider_registry=registry,
        )

        result = await service.generate_script_from_content_item(
            sample_content_item,
            target="instagram_reel",
        )

        assert result.title == "OpenAI title"
        assert fallback.calls


class TestMediaProviderSelection:
    """Tests for voice/video provider routing."""

    @pytest.mark.asyncio
    async def test_generate_video_from_script_uses_voice_and_video_providers(
        self, mock_prod_settings, sample_video_script
    ):
        """Media generation should route through selected voice and video providers."""
        voice_provider = DummyVoiceProvider("openai_tts", b"voice-bytes")
        video_provider = DummyVideoProvider(
            "tavus",
            video_id="video_123",
            video_url="https://example.com/video.mp4",
        )

        voice_registry = ProviderRegistry(provider_kind="voice")
        voice_registry.register("openai_tts", voice_provider)
        video_registry = ProviderRegistry(provider_kind="video")
        video_registry.register("tavus", video_provider)
        mock_heygen_client = MagicMock()
        mock_heygen_client.upload_audio.return_value = AudioAsset(
            url="https://example.com/audio.mp3",
            asset_id="asset_123",
        )

        settings = SimpleNamespace(
            env="prod",
            default_voice_provider="openai_tts",
            voice_provider_fallbacks=["elevenlabs"],
            default_video_provider="tavus",
            video_provider_fallbacks=["heygen"],
            enable_provider_fallbacks=True,
            heygen_video_width=1080,
            heygen_video_height=1920,
        )

        service = MediaService(
            heygen_client=mock_heygen_client,
            voice_provider_registry=voice_registry,
            video_provider_registry=video_registry,
            settings=settings,
        )

        result = await service.generate_video_from_script(
            sample_video_script,
            target="instagram_reel",
        )

        assert result.audio_data == b"voice-bytes"
        assert result.video_id == "video_123"
        assert result.video_url == "https://example.com/video.mp4"
        assert result.provider_metadata["target"] == "instagram_reel"
        assert result.provider_metadata["voice_provider"] == "openai_tts"
        assert result.provider_metadata["video_provider"] == "tavus"
        assert voice_provider.calls
        assert video_provider.calls

    def test_build_render_profile_for_instagram_reel(self, mock_prod_settings):
        """Render profiles should normalize target-specific dimensions and captions."""
        service = MediaService(settings=mock_prod_settings)

        profile = service.build_render_profile("instagram_reel")

        assert profile.name == "instagram_reel"
        assert profile.aspect_ratio == "9:16"
        assert profile.width == 1080
        assert profile.height == 1920
        assert profile.enable_captions is True
