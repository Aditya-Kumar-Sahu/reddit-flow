"""
Unit tests for generic pipeline models.

These tests cover the canonical source-agnostic request/result layer that
coexists with the legacy Reddit-specific workflow.
"""

from reddit_flow.models import (
    ChannelSpec,
    ContentItem,
    DestinationSpec,
    PipelineEvent,
    PipelineRequest,
    PipelineResult,
    ProviderSelection,
    PublishResult,
)
from reddit_flow.services.workflow_orchestrator import WorkflowStatus


class TestContentItem:
    """Tests for canonical content items."""

    def test_text_content_combines_title_and_body(self):
        """Title and body should be exposed as a renderable text block."""
        item = ContentItem(
            source_type="medium_article",
            source_id="story-123",
            source_url="https://medium.com/@author/story-123",
            title="Why Pipelines Matter",
            body="A short article body.",
        )

        assert item.text_content == "Why Pipelines Matter\n\nA short article body."

    def test_text_content_returns_title_when_body_missing(self):
        """Title-only content should still be renderable."""
        item = ContentItem(
            source_type="reddit",
            source_id="abc123",
            source_url="https://reddit.com/r/python/comments/abc123/test",
            title="Interesting thread",
        )

        assert item.text_content == "Interesting thread"


class TestPipelineRequest:
    """Tests for pipeline requests."""

    def test_defaults_include_youtube_destination_and_provider_defaults(self):
        """A minimal request should be ready for the legacy YouTube flow."""
        request = PipelineRequest(
            source_url="https://reddit.com/r/python/comments/abc123/test",
        )

        assert request.destinations == [DestinationSpec(name="youtube")]
        assert request.provider_selection == ProviderSelection()
        assert request.primary_destination == "youtube"

    def test_request_preserves_channel_and_user_input(self):
        """Requests should retain messaging-channel context."""
        request = PipelineRequest(
            source_url="https://reddit.com/r/python/comments/abc123/test",
            user_input="Focus on the top comments",
            channel=ChannelSpec(name="telegram", conversation_id="chat-1", user_id="user-1"),
            destinations=[DestinationSpec(name="instagram", export_only=True)],
        )

        assert request.user_input == "Focus on the top comments"
        assert request.channel is not None
        assert request.channel.name == "telegram"
        assert request.destinations[0].export_only is True


class TestPipelineResult:
    """Tests for pipeline execution results."""

    def test_primary_publish_url_uses_first_publish_result(self):
        """Pipeline results should expose the first destination URL conveniently."""
        result = PipelineResult(
            workflow_id="wf_001",
            status=WorkflowStatus.COMPLETED,
            publish_results=[
                PublishResult(
                    destination="youtube",
                    external_id="yt_123",
                    url="https://youtube.com/watch?v=yt_123",
                    title="Uploaded Video",
                )
            ],
        )

        assert result.primary_publish_url == "https://youtube.com/watch?v=yt_123"

    def test_events_are_stored_in_order(self):
        """Events should be preserved as part of the pipeline result."""
        result = PipelineResult(
            workflow_id="wf_002",
            status=WorkflowStatus.IN_PROGRESS,
            events=[
                PipelineEvent(
                    event_type="status", step="fetch_content", message="Fetching content"
                ),
                PipelineEvent(event_type="status", step="generate_script", message="Generating"),
            ],
        )

        assert [event.step for event in result.events] == ["fetch_content", "generate_script"]
