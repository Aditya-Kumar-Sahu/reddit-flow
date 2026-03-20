"""Telegram channel adapter for the Reddit-Flow bot."""

from __future__ import annotations

import re
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import InvalidURLError, RedditFlowError
from reddit_flow.models import ChannelSpec, DestinationSpec, PipelineEvent, PipelineRequest
from reddit_flow.pipeline.registry import SourceAdapterRegistry
from reddit_flow.services.workflow_orchestrator import WorkflowOrchestrator, WorkflowStatus

from .state import ConversationStateManager

logger = get_logger(__name__)

REDDIT_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.|old\.)?reddit\.com/r/([^/]+)/comments/([a-z0-9]+)/?",
    re.IGNORECASE,
)


class TelegramChannel:
    """Telegram adapter that preserves the legacy Reddit flow."""

    def __init__(
        self,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        settings: Optional[Settings] = None,
        state_manager: Optional[ConversationStateManager] = None,
        source_registry: Optional[SourceAdapterRegistry] = None,
    ) -> None:
        self.orchestrator = orchestrator or WorkflowOrchestrator()
        self.settings = settings or Settings()
        self.state_manager = state_manager or ConversationStateManager()
        self.source_registry = source_registry
        logger.info("TelegramChannel initialized")

    def extract_url_and_opinion(self, text: str) -> tuple[str, Optional[str]]:
        """Extract a Reddit URL and optional user opinion from a Telegram message."""
        match = REDDIT_URL_PATTERN.search(text)
        if not match:
            raise InvalidURLError("No valid Reddit URL found in message")

        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url

        remaining = text[match.end() :].strip()
        return url, remaining or None

    def _format_progress_message(self, current_step: int, extra_info: str = "") -> str:
        steps = [
            "Parsing URL",
            "Fetching Reddit content",
            "Generating AI script",
            "Generating media",
            "Publishing destination",
        ]
        lines = ["Starting processing...\n"]
        for index, step_name in enumerate(steps, start=1):
            if index < current_step:
                lines.append(f"[done] Step {index}/{len(steps)}: {step_name}")
            elif index == current_step:
                lines.append(f"[current] Step {index}/{len(steps)}: {step_name}...")
            else:
                lines.append(f"[pending] Step {index}/{len(steps)}: {step_name}")
        if extra_info:
            lines.append(f"\n{extra_info}")
        return "\n".join(lines)

    def _parse_step_from_event(self, event: PipelineEvent) -> int:
        mapping = {
            "resolve_source": 1,
            "fetch_content": 2,
            "generate_script": 3,
            "generate_media": 4,
            "publish_": 5,
            "completed": 5,
        }
        for prefix, step in mapping.items():
            if event.step.startswith(prefix):
                return step
        return 1

    async def _send_status(
        self,
        update: Update,
        message: str,
        status_message: Optional[object] = None,
    ) -> object:
        if status_message:
            try:
                await status_message.edit_text(message)  # type: ignore[attr-defined]
                return status_message
            except Exception as exc:
                logger.debug("Failed to edit Telegram status message: %s", exc)
        if update.message:
            return await update.message.reply_text(message)
        return None  # type: ignore[return-value]

    async def _emit_progress(
        self, status_message: object, event: PipelineEvent, current_step: int
    ) -> int:
        new_step = self._parse_step_from_event(event)
        if new_step > current_step:
            current_step = new_step
        try:
            await status_message.edit_text(  # type: ignore[attr-defined]
                self._format_progress_message(current_step=current_step)
            )
        except Exception as exc:
            logger.debug("Failed to update Telegram progress message: %s", exc)
        return current_step

    async def process_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process a Telegram message and run the generic pipeline."""
        if not update.message or not update.message.text:
            return

        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else 0
        channel = ChannelSpec(name="telegram", conversation_id=str(chat_id), user_id=str(user_id))

        if not self.state_manager.try_acquire(channel):
            await update.message.reply_text(
                "You already have an operation in progress. Please wait for it to complete."
            )
            return

        try:
            url, user_opinion = self.extract_url_and_opinion(update.message.text)
        except InvalidURLError:
            self.state_manager.release(channel)
            await update.message.reply_text(
                "I couldn't find a valid Reddit URL in your message.\n\n"
                "Please send a link like:\n"
                "https://reddit.com/r/subreddit/comments/abc123/"
            )
            return

        status_msg = await update.message.reply_text(
            self._format_progress_message(
                current_step=1,
                extra_info=f"URL: {url[:50]}...\nOpinion: {'Yes' if user_opinion else 'None'}",
            )
        )
        current_step = 1

        try:

            async def event_callback(event: PipelineEvent) -> None:
                nonlocal current_step
                current_step = await self._emit_progress(status_msg, event, current_step)

            request = PipelineRequest(
                source_url=url,
                user_input=user_opinion,
                channel=channel,
                destinations=[DestinationSpec(name="youtube")],
            )
            result = await self.orchestrator.process_request(request, event_callback=event_callback)

            if result.status == WorkflowStatus.COMPLETED and result.primary_publish_url:
                lines = ["Video successfully created and uploaded!\n"]
                for index, step_name in enumerate(
                    [
                        "Parsing URL",
                        "Fetching content",
                        "Generating script",
                        "Generating media",
                        "Publishing destination",
                    ],
                    start=1,
                ):
                    lines.append(f"Step {index}/5: {step_name}")
                lines.extend(
                    [
                        f"\nPublish URL: {result.primary_publish_url}",
                        (
                            f"Processing time: {result.duration_seconds:.1f}s"
                            if result.duration_seconds
                            else "Processing complete"
                        ),
                        "\nThank you for using Reddit-to-YouTube Bot!",
                    ]
                )
                await self._send_status(update, "\n".join(lines), status_msg)
            else:
                error_msg = result.error or "Unknown error occurred"
                await self._send_status(
                    update, f"Video generation failed:\n{error_msg}", status_msg
                )

        except RedditFlowError as exc:
            logger.error("Workflow error: %s", exc)
            await self._send_status(update, f"Error: {exc}", status_msg)
        except Exception as exc:
            logger.exception("Unexpected error: %s", exc)
            await self._send_status(
                update,
                "An unexpected error occurred. Please try again later.",
                status_msg,
            )
        finally:
            self.state_manager.release(channel)

    def verify_services(self) -> None:
        """Verify external services are reachable in production mode."""
        if self.settings.env != "prod":
            logger.info("Skipping service verification in %s environment", self.settings.env)
            return

        logger.info("Verifying external services...")
        self.orchestrator.content_service.reddit_client.verify_service()
        self.orchestrator.script_service.gemini_client.verify_service()
        self.orchestrator.media_service.elevenlabs_client.verify_service()
        self.orchestrator.media_service.heygen_client.verify_service()
        self.orchestrator.upload_service.youtube_client.verify_service()
        logger.info("Services verification complete")


class WorkflowManager(TelegramChannel):
    """Backward-compatible Telegram workflow wrapper."""

    pass
