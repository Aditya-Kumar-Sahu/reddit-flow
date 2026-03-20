"""Phase 5 tests for Telegram and WhatsApp channel adapters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from reddit_flow.channels.state import ConversationStateManager
from reddit_flow.channels.telegram_channel import TelegramChannel
from reddit_flow.channels.whatsapp_channel import WhatsAppChannel
from reddit_flow.exceptions import InvalidURLError
from reddit_flow.models import ChannelSpec, PipelineEvent, PipelineResult
from reddit_flow.services.workflow_orchestrator import WorkflowStatus


class TestConversationStateManager:
    """Conversation state should be keyed by channel plus conversation/user ids."""

    def test_keys_are_namespaced_by_channel(self):
        manager = ConversationStateManager()
        telegram_key = manager.build_key(
            ChannelSpec(name="telegram", conversation_id="chat-1", user_id="u1")
        )
        whatsapp_key = manager.build_key(
            ChannelSpec(name="whatsapp", conversation_id="chat-1", user_id="u1")
        )

        assert telegram_key != whatsapp_key
        assert manager.try_acquire(
            ChannelSpec(name="telegram", conversation_id="chat-1", user_id="u1")
        )
        assert not manager.try_acquire(
            ChannelSpec(name="telegram", conversation_id="chat-1", user_id="u1")
        )
        manager.release(ChannelSpec(name="telegram", conversation_id="chat-1", user_id="u1"))
        assert manager.try_acquire(
            ChannelSpec(name="telegram", conversation_id="chat-1", user_id="u1")
        )


class TestTelegramChannel:
    """Telegram channel should preserve the legacy user-facing behavior."""

    def test_extract_url_and_opinion(self):
        channel = TelegramChannel(orchestrator=MagicMock())

        url, opinion = channel.extract_url_and_opinion(
            "https://reddit.com/r/python/comments/abc123/ This is wild"
        )

        assert url == "https://reddit.com/r/python/comments/abc123/"
        assert opinion == "This is wild"

    def test_extract_url_and_opinion_raises_for_missing_url(self):
        channel = TelegramChannel(orchestrator=MagicMock())

        with pytest.raises(InvalidURLError):
            channel.extract_url_and_opinion("No link here")

    @pytest.mark.asyncio
    async def test_process_request_uses_channel_state_and_emits_final_result(self):
        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(
            return_value=PipelineResult(
                workflow_id="wf_1",
                status=WorkflowStatus.COMPLETED,
                publish_results=[],
                events=[
                    PipelineEvent(event_type="status", step="resolve_source", message="Resolving"),
                    PipelineEvent(event_type="completed", step="completed", message="Done"),
                ],
                completed_at=None,
            )
        )
        channel = TelegramChannel(orchestrator=orchestrator)
        messages = []
        edits = []

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=11, username="alice"),
            effective_chat=SimpleNamespace(id=99),
            message=SimpleNamespace(
                text="https://reddit.com/r/python/comments/abc123/ Nice",
                reply_text=AsyncMock(
                    side_effect=lambda text: messages.append(text)
                    or SimpleNamespace(
                        edit_text=AsyncMock(side_effect=lambda text: edits.append(text))
                    )
                ),
            ),
        )
        context = SimpleNamespace()

        await channel.process_request(update, context)

        assert orchestrator.process_request.await_count == 1
        assert messages
        assert edits

    @pytest.mark.asyncio
    async def test_process_request_rejects_duplicate_jobs(self):
        orchestrator = MagicMock()
        channel = TelegramChannel(orchestrator=orchestrator)
        channel.state_manager.try_acquire = MagicMock(return_value=False)
        reply = AsyncMock()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=11, username="alice"),
            effective_chat=SimpleNamespace(id=99),
            message=SimpleNamespace(
                text="https://reddit.com/r/python/comments/abc123/", reply_text=reply
            ),
        )

        await channel.process_request(update, SimpleNamespace())

        reply.assert_awaited()
        orchestrator.process_request.assert_not_called()


class TestWhatsAppChannel:
    """WhatsApp channel should accept link/text input and emit progress/final results."""

    @pytest.mark.asyncio
    async def test_handle_text_message_runs_pipeline_and_returns_result(self):
        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(
            return_value=PipelineResult(
                workflow_id="wf_2",
                status=WorkflowStatus.COMPLETED,
                publish_results=[],
                events=[
                    PipelineEvent(event_type="status", step="resolve_source", message="Resolving")
                ],
                completed_at=None,
            )
        )
        channel = WhatsAppChannel(orchestrator=orchestrator)
        sent = []

        async def send_text(text):
            sent.append(text)

        await channel.handle_text(
            text="https://reddit.com/r/python/comments/abc123/ Look at this",
            user_id="u1",
            conversation_id="c1",
            send_text=send_text,
        )

        assert orchestrator.process_request.await_count == 1
        assert sent

    def test_verify_webhook_accepts_expected_token(self):
        channel = WhatsAppChannel(orchestrator=MagicMock(), verify_token="secret-token")

        assert (
            channel.verify_webhook(mode="subscribe", token="secret-token", challenge="abc") == "abc"
        )
        assert channel.verify_webhook(mode="subscribe", token="bad-token", challenge="abc") is None
