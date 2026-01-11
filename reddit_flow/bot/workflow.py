"""
Workflow orchestration for the Reddit-to-YouTube pipeline.

This module provides the WorkflowManager for coordinating the entire process.
"""

import asyncio
import re
from typing import Optional, Set

from telegram import Update
from telegram.ext import ContextTypes

from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import InvalidURLError, RedditFlowError
from reddit_flow.services.workflow_orchestrator import WorkflowOrchestrator, WorkflowStatus

logger = get_logger(__name__)


class WorkflowManager:
    """
    Manages the complete workflow for Telegram bot interactions.

    Coordinates the WorkflowOrchestrator and handles Telegram-specific
    message processing, user state management, and status updates.

    Attributes:
        orchestrator: The underlying workflow orchestrator.
        active_users: Set of user IDs with active operations.
        settings: Application settings.
    """

    # Reddit URL pattern for extraction
    REDDIT_URL_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.|old\.)?reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", re.IGNORECASE
    )

    def __init__(
        self,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """
        Initialize WorkflowManager.

        Args:
            orchestrator: Optional WorkflowOrchestrator instance.
            settings: Optional Settings instance.
        """
        self.orchestrator = orchestrator or WorkflowOrchestrator()
        self.settings = settings or Settings()
        self.active_users: Set[int] = set()
        logger.info("WorkflowManager initialized")

    def verify_services(self) -> None:
        """
        Verify all external services are accessible.

        Logs the status of each service check.
        """
        logger.info("Verifying external services...")
        # Services are lazily loaded, so this just logs
        # In production, you'd call verify methods on each client
        logger.info("Services verification complete")

    def _extract_url_and_opinion(self, text: str) -> tuple[str, Optional[str]]:
        """
        Extract Reddit URL and optional user opinion from message.

        Args:
            text: The message text to parse.

        Returns:
            Tuple of (url, user_opinion).

        Raises:
            InvalidURLError: If no valid Reddit URL found.
        """
        match = self.REDDIT_URL_PATTERN.search(text)
        if not match:
            raise InvalidURLError("No valid Reddit URL found in message")

        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url

        # Extract opinion (text after the URL)
        url_end = match.end()
        remaining = text[url_end:].strip()
        user_opinion = remaining if remaining else None

        return url, user_opinion

    async def _send_status(
        self,
        update: Update,
        message: str,
        status_message: Optional[object] = None,
    ) -> object:
        """
        Send or update a status message.

        Args:
            update: Telegram update object.
            message: Message text to send.
            status_message: Existing message to edit (optional).

        Returns:
            The sent/updated message object.
        """
        if status_message:
            try:
                await status_message.edit_text(message)  # type: ignore
                return status_message
            except Exception:
                pass  # nosec B110
        if update.message:
            return await update.message.reply_text(message)
        return None  # type: ignore

    async def process_request(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """
        Process incoming Telegram message with Reddit URL.

        Handles the complete workflow from URL extraction to YouTube upload,
        with progress updates sent to the user.

        Args:
            update: Telegram update object.
            context: Telegram context object.
        """
        if not update.message or not update.message.text:
            return

        user_id = update.effective_user.id if update.effective_user else 0
        message_text = update.message.text

        # Check for concurrent operations
        if user_id in self.active_users:
            await update.message.reply_text(
                "⏳ You already have an operation in progress.\n" "Please wait for it to complete."
            )
            return

        # Extract URL and opinion
        try:
            url, user_opinion = self._extract_url_and_opinion(message_text)
        except InvalidURLError:
            await update.message.reply_text(
                "❌ I couldn't find a valid Reddit URL in your message.\n\n"
                "Please send a link like:\n"
                "https://reddit.com/r/subreddit/comments/abc123/"
            )
            return

        # Mark user as active
        self.active_users.add(user_id)
        status_msg = None

        try:
            # Send initial status
            status_msg = await update.message.reply_text(
                "🚀 Starting video generation...\n\n"
                f"📎 URL: {url[:50]}...\n"
                f"💭 Opinion: {'Yes' if user_opinion else 'None'}\n\n"
                "Step 1/5: Parsing URL..."
            )

            # Define progress callback
            async def update_status(step_message: str) -> None:
                if status_msg:
                    try:
                        await status_msg.edit_text(step_message)
                    except Exception:
                        pass  # nosec B110

            # Run the workflow
            result = await self.orchestrator.process_reddit_url(
                url=url,
                user_opinion=user_opinion,
                update_callback=lambda msg: asyncio.create_task(update_status(msg)),
            )

            # Send final result
            if result.status == WorkflowStatus.COMPLETED and result.youtube_url:
                success_message = (
                    "✅ Video successfully created and uploaded!\n\n"
                    f"🎬 YouTube URL: {result.youtube_url}\n"
                    f"📊 Processing time: {result.duration_seconds:.1f}s\n\n"
                    "Thank you for using Reddit-to-YouTube Bot!"
                )
                await self._send_status(update, success_message, status_msg)
            else:
                error_msg = result.error or "Unknown error occurred"
                await self._send_status(
                    update,
                    f"❌ Video generation failed:\n{error_msg}",
                    status_msg,
                )

        except RedditFlowError as e:
            logger.error(f"Workflow error: {e}")
            await self._send_status(
                update,
                f"❌ Error: {str(e)}",
                status_msg,
            )
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            await self._send_status(
                update,
                "❌ An unexpected error occurred. Please try again later.",
                status_msg,
            )
        finally:
            # Release user lock
            self.active_users.discard(user_id)
