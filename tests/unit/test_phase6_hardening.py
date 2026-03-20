"""Phase 6 hardening tests for logging, fallbacks, and failure handling."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from reddit_flow.channels.whatsapp_channel import WhatsAppChannel
from reddit_flow.exceptions import AIGenerationError, VideoGenerationError
from reddit_flow.models import (
    ChannelSpec,
    ContentItem,
    DestinationSpec,
    PipelineEvent,
    PipelineRequest,
    PipelineResult,
    PublishResult,
    VideoScript,
)
from reddit_flow.pipeline.registry import ProviderRegistry, SourceAdapterRegistry
from reddit_flow.services.media_service import MediaGenerationResult, MediaService
from reddit_flow.services.script_service import ScriptService
from reddit_flow.services.workflow_orchestrator import WorkflowOrchestrator, WorkflowStatus


class DummySourceAdapter:
    """Source adapter used for canonical pipeline tests."""

    source_name = "medium_article"

    def __init__(self, content_item: ContentItem) -> None:
        self._content_item = content_item

    def supports(self, request: PipelineRequest) -> bool:
        """Support all requests in the test."""
        return True

    def fetch_content(self, request: PipelineRequest) -> ContentItem:
        """Return the configured content item."""
        return self._content_item


class DummyPublisher:
    """Publisher used to inspect publish requests."""

    destination_name = "instagram"

    def __init__(self, result: PublishResult | None = None, error: Exception | None = None) -> None:
        self.result = result or PublishResult(
            destination="instagram",
            url="https://instagram.com/reel/ig_123",
        )
        self.error = error
        self.calls = []

    def publish(self, request):
        """Record the request and return or raise."""
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class DummyScriptProvider:
    """Simple script provider used for fallback tests."""

    def __init__(self, name: str, script: VideoScript, error: Exception | None = None) -> None:
        self.provider_name = name
        self.script = script
        self.error = error
        self.calls = []

    async def generate_script(self, content, request):
        """Generate a script or raise to force fallback."""
        self.calls.append((content, request))
        if self.error is not None:
            raise self.error
        return self.script


def build_content_item(partial: bool = False) -> ContentItem:
    """Create canonical content for hardening tests."""
    body = "" if partial else "A reusable article body."
    return ContentItem(
        source_type="medium_article",
        source_id="story-123",
        source_url="https://medium.com/@writer/story-123",
        title="A Medium Story",
        body=body,
        summary="Summary text",
        partial=partial,
    )


class TestWorkflowHardening:
    """Workflow-level hardening tests."""

    @pytest.mark.asyncio
    async def test_process_request_uses_instagram_target_for_script_and_media(self):
        """Instagram destinations should drive Instagram-specific script and render targets."""
        script_service = MagicMock()
        script_service.generate_script = AsyncMock()
        script_service.generate_script_from_content_item = AsyncMock(
            return_value=VideoScript(
                script="A reel-ready script.",
                title="Instagram Reel",
                source_post_id="story-123",
                source_subreddit="medium_article",
            )
        )
        media_service = MagicMock()
        media_service.generate_video_from_script = AsyncMock(
            return_value=MediaGenerationResult(
                audio_data=b"audio",
                audio_asset=MagicMock(),
                video_id="video_123",
                video_url="https://example.com/video.mp4",
                provider_metadata={"voice_provider": "elevenlabs", "video_provider": "heygen"},
            )
        )
        publisher = DummyPublisher()
        publisher_registry = ProviderRegistry(provider_kind="publisher")
        publisher_registry.register("instagram", publisher)
        orchestrator = WorkflowOrchestrator(
            content_service=MagicMock(),
            script_service=script_service,
            media_service=media_service,
            upload_service=MagicMock(),
            source_registry=SourceAdapterRegistry(
                adapters=[DummySourceAdapter(build_content_item())]
            ),
            publisher_registry=publisher_registry,
        )

        await orchestrator.process_request(
            PipelineRequest(
                source_url="https://medium.com/@writer/story-123",
                channel=ChannelSpec(name="whatsapp", conversation_id="chat-1", user_id="user-1"),
                destinations=[DestinationSpec(name="instagram")],
            )
        )

        assert script_service.generate_script_from_content_item.await_args.kwargs["target"] == (
            "instagram_reel"
        )
        assert media_service.generate_video_from_script.await_args.kwargs["target"] == (
            "instagram_reel"
        )

    @pytest.mark.asyncio
    async def test_process_request_emits_error_event_for_source_resolution_failure(self):
        """Source resolution failures should emit a structured error event before raising."""
        captured_events: list[PipelineEvent] = []
        orchestrator = WorkflowOrchestrator(
            content_service=MagicMock(),
            script_service=MagicMock(),
            media_service=MagicMock(),
            upload_service=MagicMock(),
            source_registry=SourceAdapterRegistry(),
        )

        async def capture_event(event: PipelineEvent) -> None:
            captured_events.append(event)

        with pytest.raises(LookupError):
            await orchestrator.process_request(
                PipelineRequest(source_url="https://example.com/unknown"),
                event_callback=capture_event,
            )

        assert [event.step for event in captured_events] == ["resolve_source", "failed"]
        assert captured_events[-1].event_type == "error"
        assert captured_events[-1].metadata["error_type"] == "LookupError"

    @pytest.mark.asyncio
    async def test_process_request_logs_structured_pipeline_context(self, caplog):
        """Completion logs should include the Phase 6 structured logging fields."""
        script_service = MagicMock()
        script_service.generate_script = AsyncMock()
        script_service.generate_script_from_content_item = AsyncMock(
            return_value=VideoScript(
                script="A generic script.",
                title="Logged Script",
                source_post_id="story-123",
                source_subreddit="medium_article",
            )
        )
        media_service = MagicMock()
        media_service.generate_video_from_script = AsyncMock(
            return_value=MediaGenerationResult(
                audio_data=b"audio",
                audio_asset=MagicMock(),
                video_id="video_123",
                video_url="https://example.com/video.mp4",
                provider_metadata={"voice_provider": "elevenlabs", "video_provider": "heygen"},
            )
        )
        publisher_registry = ProviderRegistry(provider_kind="publisher")
        publisher_registry.register("instagram", DummyPublisher())
        orchestrator = WorkflowOrchestrator(
            content_service=MagicMock(),
            script_service=script_service,
            media_service=media_service,
            upload_service=MagicMock(),
            source_registry=SourceAdapterRegistry(
                adapters=[DummySourceAdapter(build_content_item(partial=True))]
            ),
            publisher_registry=publisher_registry,
        )

        with caplog.at_level(logging.INFO):
            await orchestrator.process_request(
                PipelineRequest(
                    source_url="https://medium.com/@writer/story-123",
                    channel=ChannelSpec(
                        name="whatsapp", conversation_id="chat-1", user_id="user-1"
                    ),
                    destinations=[DestinationSpec(name="instagram", export_only=True)],
                )
            )

        structured_records = [record for record in caplog.records if hasattr(record, "extra_data")]
        assert structured_records
        assert any(record.extra_data["partial_content"] is True for record in structured_records)
        assert any(
            {
                "source_type",
                "target_destinations",
                "channel",
                "provider_path",
                "workflow_id",
                "partial_content",
            }.issubset(record.extra_data.keys())
            for record in structured_records
        )

    @pytest.mark.asyncio
    async def test_media_timeout_emits_error_event(self):
        """Media timeouts should be surfaced through the pipeline error event stream."""
        script_service = MagicMock()
        script_service.generate_script = AsyncMock()
        script_service.generate_script_from_content_item = AsyncMock(
            return_value=VideoScript(script="Script body", title="Title")
        )
        media_service = MagicMock()
        media_service.generate_video_from_script = AsyncMock(
            side_effect=VideoGenerationError("Timed out waiting for video")
        )
        publisher_registry = ProviderRegistry(provider_kind="publisher")
        publisher_registry.register("instagram", DummyPublisher())
        orchestrator = WorkflowOrchestrator(
            content_service=MagicMock(),
            script_service=script_service,
            media_service=media_service,
            upload_service=MagicMock(),
            source_registry=SourceAdapterRegistry(
                adapters=[DummySourceAdapter(build_content_item())]
            ),
            publisher_registry=publisher_registry,
        )
        captured_events: list[PipelineEvent] = []

        async def capture_event(event: PipelineEvent) -> None:
            captured_events.append(event)

        with pytest.raises(VideoGenerationError):
            await orchestrator.process_request(
                PipelineRequest(
                    source_url="https://medium.com/@writer/story-123",
                    destinations=[DestinationSpec(name="instagram")],
                ),
                event_callback=capture_event,
            )

        assert captured_events[-1].event_type == "error"
        assert captured_events[-1].metadata["error_type"] == "VideoGenerationError"

    @pytest.mark.asyncio
    async def test_instagram_publish_failure_emits_error_event(self):
        """Publish failures should also be reflected in the pipeline event stream."""
        script_service = MagicMock()
        script_service.generate_script = AsyncMock()
        script_service.generate_script_from_content_item = AsyncMock(
            return_value=VideoScript(script="Script body", title="Title")
        )
        media_service = MagicMock()
        media_service.generate_video_from_script = AsyncMock(
            return_value=MediaGenerationResult(
                audio_data=b"audio",
                audio_asset=MagicMock(),
                video_id="video_123",
                video_url="https://example.com/video.mp4",
            )
        )
        publisher_registry = ProviderRegistry(provider_kind="publisher")
        publisher_registry.register(
            "instagram", DummyPublisher(error=RuntimeError("Instagram publish failed"))
        )
        orchestrator = WorkflowOrchestrator(
            content_service=MagicMock(),
            script_service=script_service,
            media_service=media_service,
            upload_service=MagicMock(),
            source_registry=SourceAdapterRegistry(
                adapters=[DummySourceAdapter(build_content_item())]
            ),
            publisher_registry=publisher_registry,
        )
        captured_events: list[PipelineEvent] = []

        async def capture_event(event: PipelineEvent) -> None:
            captured_events.append(event)

        with pytest.raises(RuntimeError):
            await orchestrator.process_request(
                PipelineRequest(
                    source_url="https://medium.com/@writer/story-123",
                    destinations=[DestinationSpec(name="instagram")],
                ),
                event_callback=capture_event,
            )

        assert captured_events[-1].metadata["error_type"] == "RuntimeError"


class TestProviderFallbackHardening:
    """Fallback behavior that should remain green during failures."""

    @pytest.mark.asyncio
    async def test_generate_script_from_content_item_uses_runtime_fallback_provider(
        self, mock_prod_settings
    ):
        """If the preferred provider fails, the configured fallback should be attempted."""
        failing_provider = DummyScriptProvider(
            "anthropic",
            VideoScript(script="unused", title="unused"),
            error=AIGenerationError("Primary provider failed"),
        )
        fallback_provider = DummyScriptProvider(
            "openai",
            VideoScript(script="Recovered script", title="Recovered title"),
        )
        registry = ProviderRegistry(provider_kind="script")
        registry.register("anthropic", failing_provider)
        registry.register("openai", fallback_provider)
        settings = SimpleNamespace(
            env="prod",
            default_script_provider="anthropic",
            script_provider_fallbacks=["openai"],
            enable_provider_fallbacks=True,
        )
        service = ScriptService(settings=settings, script_provider_registry=registry)

        result = await service.generate_script_from_content_item(build_content_item())

        assert result.title == "Recovered title"
        assert failing_provider.calls
        assert fallback_provider.calls


class TestWhatsAppChannelHardening:
    """WhatsApp-specific hardening behaviors."""

    @pytest.mark.asyncio
    async def test_whatsapp_channel_releases_state_when_send_fails(self):
        """Outbound send failures should not leak the conversation lock."""
        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock()
        channel = WhatsAppChannel(
            orchestrator=orchestrator,
            settings=SimpleNamespace(whatsapp_verify_token=None),
        )
        state_key = ChannelSpec(name="whatsapp", conversation_id="chat-1", user_id="user-1")

        async def failing_send_text(text: str) -> None:
            raise RuntimeError("WhatsApp send failed")

        with pytest.raises(RuntimeError):
            await channel.handle_text(
                text="https://medium.com/@writer/story-123",
                user_id="user-1",
                conversation_id="chat-1",
                send_text=failing_send_text,
            )

        assert channel.state_manager.try_acquire(state_key) is True

    @pytest.mark.asyncio
    async def test_whatsapp_channel_sends_export_bundle_manifest_when_publish_url_missing(self):
        """Export-only runs should send a useful artifact path instead of a false failure."""
        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(
            return_value=PipelineResult(
                workflow_id="wf_123",
                status=WorkflowStatus.COMPLETED,
                publish_results=[
                    PublishResult(
                        destination="instagram",
                        metadata={
                            "export_bundle": {
                                "bundle_dir": "C:/temp/instagram_bundle",
                                "manifest_path": "C:/temp/instagram_bundle/manifest.json",
                            }
                        },
                    )
                ],
            )
        )
        channel = WhatsAppChannel(
            orchestrator=orchestrator,
            settings=SimpleNamespace(whatsapp_verify_token=None),
            default_destinations=[DestinationSpec(name="instagram", export_only=True)],
        )
        sent_messages: list[str] = []

        async def send_text(text: str) -> None:
            sent_messages.append(text)

        await channel.handle_text(
            text="https://medium.com/towards-data-science",
            user_id="user-2",
            conversation_id="chat-2",
            send_text=send_text,
        )

        assert any("manifest.json" in message for message in sent_messages)


class TestMediaServiceProviderMetadata:
    """Media-service metadata should stay useful in test-mode runs."""

    @pytest.mark.asyncio
    async def test_generate_video_from_script_populates_provider_metadata_in_test_mode(self):
        """Test-mode media generation should still expose provider-path metadata."""
        settings = SimpleNamespace(
            env="test",
            default_voice_provider="elevenlabs",
            default_video_provider="heygen",
        )
        service = MediaService(settings=settings)

        result = await service.generate_video_from_script(
            VideoScript(script="Test script body", title="Test title"),
            target="instagram_reel",
        )

        assert result.provider_metadata["target"] == "instagram_reel"
        assert result.provider_metadata["voice_provider"] == "elevenlabs"
        assert result.provider_metadata["video_provider"] == "heygen"
