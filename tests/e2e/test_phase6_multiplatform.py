"""Phase 6 end-to-end tests for multi-platform workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_flow.channels.telegram_channel import TelegramChannel
from reddit_flow.channels.whatsapp_channel import WhatsAppChannel
from reddit_flow.models import (
    AudioAsset,
    ContentItem,
    DestinationSpec,
    RedditComment,
    RedditPost,
    VideoScript,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
)
from reddit_flow.pipeline.publishers import InstagramPublisher
from reddit_flow.pipeline.registry import ProviderRegistry, SourceAdapterRegistry
from reddit_flow.pipeline.sources import MediumArticleSourceAdapter, MediumFeedSourceAdapter
from reddit_flow.services.content_service import ContentService
from reddit_flow.services.instagram_export_service import InstagramExportBundleService
from reddit_flow.services.media_service import MediaService
from reddit_flow.services.script_service import ScriptService
from reddit_flow.services.upload_service import UploadService
from reddit_flow.services.workflow_orchestrator import WorkflowOrchestrator

pytestmark = [pytest.mark.e2e]


def build_prod_settings(**overrides):
    """Create a lightweight settings object for mocked end-to-end tests."""
    defaults = {
        "env": "prod",
        "temp_dir": overrides.get("temp_dir", "."),
        "default_script_provider": "gemini",
        "default_voice_provider": "elevenlabs",
        "default_video_provider": "heygen",
        "script_provider_fallbacks": [],
        "voice_provider_fallbacks": [],
        "video_provider_fallbacks": [],
        "enable_provider_fallbacks": False,
        "enable_instagram_publish": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def build_streaming_response(body: bytes = b"video-bytes") -> MagicMock:
    """Build a streaming HTTP response mock for media downloads."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.iter_content.return_value = [body]
    response.status_code = 200
    return response


class MockRedditClient:
    """Mock Reddit client for multi-platform E2E tests."""

    service_name = "Reddit"

    def __init__(self) -> None:
        self.reddit = MagicMock()

    def get_post(self, subreddit_name: str, post_id: str) -> RedditPost:
        """Return a stable Reddit post fixture."""
        return RedditPost(
            id=post_id,
            subreddit=subreddit_name,
            title="Shipping new pipeline changes safely",
            selftext="How do we refactor a social workflow without breaking Reddit?",
            url=f"https://reddit.com/r/{subreddit_name}/comments/{post_id}/",
            author="builder",
            score=240,
            comments=[
                RedditComment(id="c1", body="Start with tests.", author="qa", score=44),
                RedditComment(id="c2", body="Keep the old path green.", author="ops", score=38),
            ],
        )

    def get_post_data(self, subreddit_name: str, post_id: str) -> dict:
        """Return post data in the dictionary format used by ContentService."""
        post = self.get_post(subreddit_name, post_id)
        return {
            "id": post.id,
            "subreddit": post.subreddit,
            "title": post.title,
            "selftext": post.selftext,
            "url": post.url,
            "author": post.author,
            "score": post.score,
            "comments": [
                {
                    "id": comment.id,
                    "body": comment.body,
                    "author": comment.author,
                    "score": comment.score,
                    "depth": comment.depth,
                }
                for comment in post.comments
            ],
        }

    def verify_service(self) -> bool:
        """Pretend the client is healthy."""
        return True


class MockGeminiClient:
    """Mock script-generation client."""

    service_name = "Gemini"

    async def generate_script(
        self,
        post_text: str,
        comments_data: list,
        user_opinion: str | None = None,
        source_post_id: str | None = None,
        source_subreddit: str | None = None,
    ) -> VideoScript:
        """Return a deterministic script for the mocked pipeline."""
        return VideoScript(
            title="Multi-platform pipeline update",
            script=(
                "We kept the legacy flow stable, added canonical content models, "
                "and routed the new destinations through one orchestrator."
            ),
            source_post_id=source_post_id,
            source_subreddit=source_subreddit,
            user_opinion=user_opinion,
        )

    def verify_service(self) -> bool:
        """Pretend the client is healthy."""
        return True


class MockElevenLabsClient:
    """Mock TTS client."""

    service_name = "ElevenLabs"

    def text_to_speech(self, text: str) -> bytes:
        """Return fake MP3 bytes."""
        return b"\xff\xfb\x90\x00" + b"\x00" * 256

    def verify_service(self) -> bool:
        """Pretend the client is healthy."""
        return True


class MockHeyGenClient:
    """Mock avatar video client."""

    service_name = "HeyGen"

    def upload_audio(self, audio_data: bytes, content_type: str = "audio/mpeg") -> AudioAsset:
        """Return a fake uploaded audio asset."""
        return AudioAsset(url="https://example.com/audio.mp3", asset_id="audio_123")

    def generate_video(
        self,
        audio_url: str,
        title: str | None = None,
        avatar_id: str | None = None,
        avatar_style: str = "normal",
        test_mode: bool | None = None,
        enable_captions: bool = True,
    ) -> str:
        """Return a fake video id."""
        return "video_123"

    async def wait_for_video(
        self,
        video_id: str,
        update_callback=None,
        timeout: int | None = None,
    ) -> str:
        """Return a completed video URL."""
        if update_callback is not None:
            await update_callback("Video complete!")
        return "https://example.com/generated-video.mp4"

    def verify_service(self) -> bool:
        """Pretend the client is healthy."""
        return True


class MockYouTubeClient:
    """Mock YouTube client."""

    service_name = "YouTube"

    def upload_video_from_request(
        self,
        request: YouTubeUploadRequest,
        progress_callback=None,
    ) -> YouTubeUploadResponse:
        """Return a fake YouTube upload response."""
        if progress_callback is not None:
            progress_callback(100)
        return YouTubeUploadResponse(
            video_id="yt_123",
            title=request.title,
            url="https://www.youtube.com/watch?v=yt_123",
            uploaded_at=datetime.now(),
        )

    def verify_service(self) -> bool:
        """Pretend the client is healthy."""
        return True


class MockMediumClient:
    """Mock Medium client that can serve article and feed content."""

    def __init__(self, article_item: ContentItem) -> None:
        self.article_item = article_item

    def normalize_url(self, url: str) -> str:
        """Normalize URLs for the feed adapter helper."""
        return url.rstrip("/")

    def fetch_article_content(self, url: str) -> ContentItem:
        """Return the configured article item."""
        return self.article_item.model_copy(update={"source_url": url})

    def fetch_latest_feed_article(self, url: str) -> ContentItem:
        """Return the configured article item for feed resolution."""
        return self.article_item.model_copy(update={"source_url": url})


class MockInstagramClient:
    """Mock Instagram direct-publish client."""

    def create_media_container(
        self,
        media_path: str,
        caption: str,
        hashtags: str,
        metadata: dict,
    ) -> str:
        """Return a fake media container id."""
        return "container_123"

    def publish_media_container(self, container_id: str) -> str:
        """Return a fake reel id."""
        return "ig_123"

    def build_permalink(self, publish_id: str) -> str:
        """Build a stable mock permalink."""
        return f"https://instagram.com/reel/{publish_id}"


def build_reddit_orchestrator() -> WorkflowOrchestrator:
    """Create a Reddit -> YouTube orchestrator with mocked services."""
    settings = build_prod_settings()
    content_service = ContentService(reddit_client=MockRedditClient())
    script_service = ScriptService(gemini_client=MockGeminiClient(), settings=settings)
    media_service = MediaService(
        elevenlabs_client=MockElevenLabsClient(),
        heygen_client=MockHeyGenClient(),
        settings=settings,
    )
    upload_service = UploadService(youtube_client=MockYouTubeClient(), settings=settings)
    return WorkflowOrchestrator(
        content_service=content_service,
        script_service=script_service,
        media_service=media_service,
        upload_service=upload_service,
    )


def build_medium_orchestrator(
    article_item: ContentItem,
    publisher: InstagramPublisher,
    source_kind: str,
) -> WorkflowOrchestrator:
    """Create a Medium -> Instagram orchestrator with mocked services."""
    settings = build_prod_settings()
    medium_client = MockMediumClient(article_item)
    source_registry = SourceAdapterRegistry(
        adapters=[
            (
                MediumFeedSourceAdapter(medium_client)
                if source_kind == "feed"
                else MediumArticleSourceAdapter(medium_client)
            )
        ]
    )
    publisher_registry = ProviderRegistry(provider_kind="publisher")
    publisher_registry.register("instagram", publisher)
    script_service = ScriptService(gemini_client=MockGeminiClient(), settings=settings)
    media_service = MediaService(
        elevenlabs_client=MockElevenLabsClient(),
        heygen_client=MockHeyGenClient(),
        settings=settings,
    )

    return WorkflowOrchestrator(
        content_service=MagicMock(),
        script_service=script_service,
        media_service=media_service,
        upload_service=MagicMock(),
        source_registry=source_registry,
        publisher_registry=publisher_registry,
    )


class TestPhase6EndToEndFlows:
    """Cross-platform Phase 6 coverage."""

    @pytest.mark.asyncio
    async def test_reddit_to_youtube_to_telegram(self):
        """The legacy Reddit path should still complete through Telegram."""
        orchestrator = build_reddit_orchestrator()
        channel = TelegramChannel(orchestrator=orchestrator, settings=build_prod_settings())
        status_message = MagicMock()
        status_message.edit_text = AsyncMock()
        reply_text = AsyncMock(side_effect=[status_message])
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=42, username="alice"),
            effective_chat=SimpleNamespace(id=7),
            message=SimpleNamespace(
                text="https://reddit.com/r/python/comments/abc123/ keep the migration safe",
                reply_text=reply_text,
            ),
        )

        with patch("requests.get", return_value=build_streaming_response()):
            await channel.process_request(update, SimpleNamespace())

        assert reply_text.await_count >= 1
        assert status_message.edit_text.await_count >= 1
        final_message = status_message.edit_text.await_args_list[-1].args[0]
        assert "youtube.com/watch" in final_message

    @pytest.mark.asyncio
    async def test_medium_article_to_instagram_to_whatsapp(self, tmp_path: Path):
        """Medium article requests should publish to Instagram and report back over WhatsApp."""
        article_item = ContentItem(
            source_type="medium_article",
            source_id="story-123",
            source_url="https://medium.com/@writer/story-123",
            title="A polished Medium article",
            body="This article explains how to fan content out to new channels.",
            summary="A summary for Instagram.",
            author="Writer",
        )
        publisher = InstagramPublisher(
            instagram_client=MockInstagramClient(),
            export_service=InstagramExportBundleService(output_dir=tmp_path),
            settings=build_prod_settings(enable_instagram_publish=True, temp_dir=str(tmp_path)),
        )
        orchestrator = build_medium_orchestrator(article_item, publisher, source_kind="article")
        channel = WhatsAppChannel(
            orchestrator=orchestrator,
            settings=build_prod_settings(),
            default_destinations=[DestinationSpec(name="instagram")],
        )
        sent_messages: list[str] = []

        async def send_text(text: str) -> None:
            sent_messages.append(text)

        with patch("requests.get", return_value=build_streaming_response()):
            await channel.handle_text(
                text="https://medium.com/@writer/story-123 turn this into a reel",
                user_id="user-1",
                conversation_id="chat-1",
                send_text=send_text,
            )

        assert any("instagram.com/reel/ig_123" in message for message in sent_messages)

    @pytest.mark.asyncio
    async def test_medium_feed_candidate_to_instagram_export_and_whatsapp_notification(
        self, tmp_path: Path
    ):
        """Feed-based Medium requests should export an Instagram bundle and notify WhatsApp."""
        article_item = ContentItem(
            source_type="medium_article",
            source_id="story-456",
            source_url="https://medium.com/feed/towards-data-science",
            title="A feed-resolved Medium story",
            body="This story came from a Medium publication feed.",
            summary="Feed summary",
            author="Writer",
        )
        publisher = InstagramPublisher(
            instagram_client=MockInstagramClient(),
            export_service=InstagramExportBundleService(output_dir=tmp_path),
            settings=build_prod_settings(enable_instagram_publish=False, temp_dir=str(tmp_path)),
        )
        orchestrator = build_medium_orchestrator(article_item, publisher, source_kind="feed")
        channel = WhatsAppChannel(
            orchestrator=orchestrator,
            settings=build_prod_settings(),
            default_destinations=[DestinationSpec(name="instagram", export_only=True)],
        )
        sent_messages: list[str] = []

        async def send_text(text: str) -> None:
            sent_messages.append(text)

        with patch("requests.get", return_value=build_streaming_response()):
            await channel.handle_text(
                text="https://medium.com/towards-data-science make an export bundle",
                user_id="user-2",
                conversation_id="chat-2",
                send_text=send_text,
            )

        assert any("manifest" in message.lower() for message in sent_messages)
