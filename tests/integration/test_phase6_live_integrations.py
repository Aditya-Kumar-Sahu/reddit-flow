"""Live Phase 6 integration and smoke tests."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import load_dotenv

from reddit_flow.channels.whatsapp_channel import WhatsAppChannel
from reddit_flow.clients.medium_client import MediumClient
from reddit_flow.models import ContentItem, PublishRequest, VideoScript
from reddit_flow.pipeline.publishers import InstagramPublisher
from reddit_flow.services.instagram_export_service import InstagramExportBundleService
from reddit_flow.services.script_service import ScriptService

load_dotenv()

pytestmark = [pytest.mark.integration, pytest.mark.live]


def _has_live_medium_article() -> bool:
    """Check whether a live Medium article URL is configured."""
    return bool(os.getenv("LIVE_MEDIUM_ARTICLE_URL"))


def _has_live_medium_feed() -> bool:
    """Check whether a live Medium feed source URL is configured."""
    return bool(os.getenv("LIVE_MEDIUM_FEED_URL"))


def _has_live_gemini_medium() -> bool:
    """Check whether live Medium + Gemini inputs are configured."""
    return _has_live_medium_article() and bool(os.getenv("GOOGLE_API_KEY"))


def _has_live_instagram_smoke_inputs() -> bool:
    """Check whether the live Instagram smoke inputs are configured."""
    return bool(
        os.getenv("INSTAGRAM_ACCESS_TOKEN")
        and os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        and os.getenv("LIVE_INSTAGRAM_MEDIA_URL")
    )


def _has_live_whatsapp_inputs() -> bool:
    """Check whether the live WhatsApp webhook inputs are configured."""
    return bool(os.getenv("WHATSAPP_VERIFY_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"))


class RecordingInstagramClient:
    """A recording client used for live contract smoke tests."""

    def __init__(self) -> None:
        self.media_path: str | None = None
        self.caption: str | None = None
        self.hashtags: str | None = None

    def create_media_container(
        self,
        media_path: str,
        caption: str,
        hashtags: str,
        metadata: dict,
    ) -> str:
        """Record the direct-publish inputs."""
        self.media_path = media_path
        self.caption = caption
        self.hashtags = hashtags
        return "container_live"

    def publish_media_container(self, container_id: str) -> str:
        """Return a fake publish id for the smoke test."""
        return "ig_live"


class TestPhase6LiveIntegrations:
    """Live or credential-gated smoke tests for the new pipeline surface."""

    @pytest.mark.skipif(
        not _has_live_medium_article(),
        reason="LIVE_MEDIUM_ARTICLE_URL is not configured",
    )
    def test_live_medium_article_fetch(self):
        """Fetch a real Medium article into the canonical content model."""
        client = MediumClient(
            {
                "user_agent": os.getenv("MEDIUM_USER_AGENT", "reddit-flow/0.1"),
                "timeout": int(os.getenv("MEDIUM_REQUEST_TIMEOUT", "30")),
            }
        )

        item = client.fetch_article_content(os.environ["LIVE_MEDIUM_ARTICLE_URL"])

        assert isinstance(item, ContentItem)
        assert item.title
        assert item.source_type == "medium_article"

    @pytest.mark.skipif(
        not _has_live_medium_feed(),
        reason="LIVE_MEDIUM_FEED_URL is not configured",
    )
    def test_live_medium_feed_fetch(self):
        """Fetch a real Medium feed into canonical candidates."""
        client = MediumClient(
            {
                "user_agent": os.getenv("MEDIUM_USER_AGENT", "reddit-flow/0.1"),
                "timeout": int(os.getenv("MEDIUM_REQUEST_TIMEOUT", "30")),
            }
        )

        candidates = client.fetch_feed_candidates(os.environ["LIVE_MEDIUM_FEED_URL"])

        assert candidates
        assert candidates[0].title
        assert candidates[0].url.startswith("https://")

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not _has_live_gemini_medium(),
        reason="GOOGLE_API_KEY or LIVE_MEDIUM_ARTICLE_URL is not configured",
    )
    async def test_live_gemini_script_generation_from_medium_article(self):
        """Run the generic script service against a real Medium article."""
        client = MediumClient(
            {
                "user_agent": os.getenv("MEDIUM_USER_AGENT", "reddit-flow/0.1"),
                "timeout": int(os.getenv("MEDIUM_REQUEST_TIMEOUT", "30")),
            }
        )
        content_item = client.fetch_article_content(os.environ["LIVE_MEDIUM_ARTICLE_URL"])
        service = ScriptService(
            settings=SimpleNamespace(
                env="prod",
                default_script_provider="gemini",
                script_provider_fallbacks=[],
                enable_provider_fallbacks=False,
            )
        )

        script = await service.generate_script_from_content_item(
            content_item,
            target="instagram_reel",
        )

        assert script.title
        assert script.script
        assert script.word_count > 0

    @pytest.mark.skipif(
        not _has_live_instagram_smoke_inputs(),
        reason=(
            "INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID, or "
            "LIVE_INSTAGRAM_MEDIA_URL is not configured"
        ),
    )
    def test_live_instagram_publish_contract_smoke(self, tmp_path: Path):
        """Exercise the direct-publish contract with live config and a public media URL."""
        client = RecordingInstagramClient()
        publisher = InstagramPublisher(
            instagram_client=client,
            export_service=InstagramExportBundleService(output_dir=tmp_path),
            settings=SimpleNamespace(env="prod", enable_instagram_publish=True),
        )

        result = publisher.publish(
            PublishRequest(
                destination="instagram",
                media_url=os.environ["LIVE_INSTAGRAM_MEDIA_URL"],
                script=VideoScript(
                    script="A live smoke-test script for Instagram export.",
                    title="Instagram smoke test",
                    source_post_id="live-smoke",
                    source_subreddit="medium_article",
                ),
                content_item=ContentItem(
                    source_type="medium_article",
                    source_id="live-smoke",
                    source_url=os.environ.get("LIVE_MEDIUM_ARTICLE_URL", "https://medium.com"),
                    title="Instagram smoke content",
                    body="Smoke-test body",
                ),
            )
        )

        assert result.external_id == "ig_live"
        assert client.media_path is not None
        assert client.caption is not None
        assert client.hashtags is not None

    @pytest.mark.skipif(
        not _has_live_whatsapp_inputs(),
        reason="WHATSAPP_VERIFY_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not configured",
    )
    def test_live_whatsapp_webhook_verification_contract(self):
        """Verify the WhatsApp webhook contract with live credentials loaded."""
        channel = WhatsAppChannel(
            settings=SimpleNamespace(whatsapp_verify_token=os.environ["WHATSAPP_VERIFY_TOKEN"]),
            verify_token=os.environ["WHATSAPP_VERIFY_TOKEN"],
        )

        assert (
            channel.verify_webhook(
                mode="subscribe",
                token=os.environ["WHATSAPP_VERIFY_TOKEN"],
                challenge="challenge-token",
            )
            == "challenge-token"
        )
