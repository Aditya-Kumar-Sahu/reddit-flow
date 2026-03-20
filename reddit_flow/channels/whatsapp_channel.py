"""WhatsApp channel adapter and webhook helpers."""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import InvalidURLError, RedditFlowError
from reddit_flow.models import (
    ChannelSpec,
    DestinationSpec,
    PipelineEvent,
    PipelineRequest,
    PipelineResult,
)
from reddit_flow.services.workflow_orchestrator import WorkflowOrchestrator, WorkflowStatus

from .state import ConversationStateManager

logger = get_logger(__name__)

URL_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/\S*)?)",
    re.IGNORECASE,
)


class WhatsAppChannel:
    """WhatsApp channel adapter for link-based pipeline requests."""

    def __init__(
        self,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        settings: Optional[Settings] = None,
        state_manager: Optional[ConversationStateManager] = None,
        verify_token: Optional[str] = None,
        default_destinations: Optional[list[DestinationSpec]] = None,
    ) -> None:
        self.orchestrator = orchestrator or WorkflowOrchestrator()
        self.settings = settings or Settings()
        self.state_manager = state_manager or ConversationStateManager()
        self.verify_token = verify_token or self._load_verify_token()
        self.default_destinations = [
            destination.model_copy()
            for destination in (default_destinations or [DestinationSpec(name="youtube")])
        ]
        logger.info("WhatsAppChannel initialized")

    def _load_verify_token(self) -> Optional[str]:
        token = getattr(self.settings, "whatsapp_verify_token", None)
        if token is None:
            return None
        if hasattr(token, "get_secret_value"):
            return token.get_secret_value()
        return str(token)

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify a WhatsApp webhook subscription challenge."""
        if mode != "subscribe":
            return None
        if self.verify_token is None or token != self.verify_token:
            return None
        return challenge

    def extract_url_and_opinion(self, text: str) -> tuple[str, Optional[str]]:
        """Extract the first URL and optional trailing opinion text."""
        match = URL_PATTERN.search(text)
        if not match:
            raise InvalidURLError("No valid URL found in message")

        raw_url = match.group(1).rstrip(".,;:!?)]}")
        parsed = urlparse(raw_url if raw_url.startswith("http") else f"https://{raw_url}")
        if not parsed.netloc:
            raise InvalidURLError("No valid URL found in message")

        opinion = text[match.end() :].strip()
        return parsed.geturl(), opinion or None

    def _build_completion_messages(self, result: PipelineResult) -> list[str]:
        """Build completion messages for publish links or export bundles."""
        messages: list[str] = []

        if result.primary_publish_url:
            messages.append(f"Done! {result.primary_publish_url}")

        for publish_result in result.publish_results:
            export_bundle = publish_result.metadata.get("export_bundle", {})
            manifest_path = export_bundle.get("manifest_path")
            bundle_dir = export_bundle.get("bundle_dir")
            local_file_path = publish_result.metadata.get("local_file_path")

            if manifest_path:
                messages.append(f"Export bundle manifest: {manifest_path}")
            elif bundle_dir:
                messages.append(f"Export bundle ready: {bundle_dir}")

            if local_file_path:
                messages.append(f"Local asset: {local_file_path}")

        if not messages:
            messages.append("Done! Processing completed without a public publish URL.")

        return messages

    async def handle_text(
        self,
        text: str,
        user_id: str,
        conversation_id: str,
        send_text: Callable[[str], Awaitable[Any]],
    ) -> None:
        """Handle an inbound WhatsApp text message."""
        channel = ChannelSpec(name="whatsapp", conversation_id=conversation_id, user_id=user_id)
        acquired = self.state_manager.try_acquire(channel)
        if not acquired:
            await send_text("You already have an operation in progress. Please wait.")
            return

        try:
            try:
                url, user_opinion = self.extract_url_and_opinion(text)
            except InvalidURLError:
                await send_text("I couldn't find a valid link in your message.")
                return

            await send_text("Starting processing for your link...")

            async def event_callback(event: PipelineEvent) -> None:
                if event.event_type == "status":
                    await send_text(event.message)

            try:
                result = await self.orchestrator.process_request(
                    PipelineRequest(
                        source_url=url,
                        user_input=user_opinion,
                        channel=channel,
                        destinations=[
                            destination.model_copy() for destination in self.default_destinations
                        ],
                    ),
                    event_callback=event_callback,
                )
            except RedditFlowError as exc:
                logger.error("WhatsApp workflow error: %s", exc)
                await send_text(f"Error: {exc}")
                return
            except Exception as exc:
                logger.exception("Unexpected WhatsApp error: %s", exc)
                await send_text("An unexpected error occurred. Please try again later.")
                raise

            if result.status == WorkflowStatus.COMPLETED:
                for message in self._build_completion_messages(result):
                    await send_text(message)
            else:
                await send_text(f"Video generation failed: {result.error or 'Unknown error'}")
        finally:
            self.state_manager.release(channel)


class WhatsAppWebhookHandler:
    """Webhook helper for WhatsApp verification and inbound events."""

    def __init__(self, channel: WhatsAppChannel) -> None:
        self.channel = channel

    def verify(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify the webhook subscription challenge from WhatsApp."""
        return self.channel.verify_webhook(mode=mode, token=token, challenge=challenge)

    async def handle_payload(
        self,
        payload: dict[str, Any],
        send_text: Callable[[str], Awaitable[Any]],
    ) -> None:
        """Handle a webhook payload containing WhatsApp inbound messages."""
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        continue
                    text = message.get("text", {}).get("body", "")
                    from_id = message.get("from", "unknown")
                    conversation_id = message.get("id", from_id)
                    await self.channel.handle_text(
                        text=text,
                        user_id=from_id,
                        conversation_id=conversation_id,
                        send_text=send_text,
                    )
