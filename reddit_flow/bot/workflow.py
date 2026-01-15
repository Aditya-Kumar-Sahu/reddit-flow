"""
Workflow orchestration for the Reddit-to-YouTube pipeline.

This module provides the WorkflowManager for coordinating the entire process.
"""

import asyncio
import re
from typing import Dict, Optional, Set

from telegram import Update
from telegram.ext import ContextTypes

from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import InvalidURLError, RedditFlowError
from reddit_flow.services.workflow_orchestrator import WorkflowOrchestrator, WorkflowStatus

logger = get_logger(__name__)

# Workflow step definitions
WORKFLOW_STEPS: Dict[int, str] = {
    1: "Parsing URL",
    2: "Fetching Reddit content",
    3: "Generating AI script",
    4: "Generating audio",
    5: "Generating video",
    6: "Uploading to YouTube",
}


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

    # Step mapping from orchestrator messages to step numbers
    STEP_MAPPING: Dict[str, int] = {
        "Step 1/5": 1,
        "Step 2/5": 2,
        "Step 3/5": 3,
        "Step 4/5: Generating audio": 4,
        "Step 4/5: Generating video": 5,
        "Step 5/5": 6,
    }

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

    def _format_progress_message(self, current_step: int, extra_info: str = "") -> str:
        """
        Format progress message showing all steps with status indicators.

        Args:
            current_step: The step currently in progress (1-6).
            extra_info: Optional extra information to append.

        Returns:
            Formatted progress message with all steps.
        """
        total_steps = len(WORKFLOW_STEPS)
        lines = ["🚀 Starting video generation...\n"]

        for step_num, step_name in WORKFLOW_STEPS.items():
            if step_num < current_step:
                # Completed step
                lines.append(f"✅ Step {step_num}/{total_steps}: {step_name}")
            elif step_num == current_step:
                # Current step (in progress)
                lines.append(f"▪️ Step {step_num}/{total_steps}: {step_name}...")
            else:
                # Pending step
                lines.append(f"⬜ Step {step_num}/{total_steps}: {step_name}")

        if extra_info:
            lines.append(f"\n{extra_info}")

        return "\n".join(lines)

    def _parse_step_from_message(self, message: str) -> int:
        """
        Parse step number from orchestrator callback message.

        Args:
            message: The callback message from orchestrator.

        Returns:
            Step number (1-6).
        """
        for pattern, step_num in self.STEP_MAPPING.items():
            if pattern in message:
                return step_num
        return 1  # Default to step 1

    def verify_services(self) -> None:
        """
        Verify all external services are accessible.

        Only runs verification checks when ENV=prod using verify_service() method
        on each client. In other environments, just logs initialized status.
        Logs the status of each service check.
        """
        if self.settings.env != "prod":
            logger.info(f"Skipping service verification in {self.settings.env} environment")
            return

        logger.info("Verifying external services...")

        try:
            # Verify Content Service (Reddit)
            self.orchestrator.content_service.reddit_client.verify_service()

            # Verify Script Service (Gemini)
            self.orchestrator.script_service.gemini_client.verify_service()

            # Verify Media Service (ElevenLabs, HeyGen)
            self.orchestrator.media_service.elevenlabs_client.verify_service()
            self.orchestrator.media_service.heygen_client.verify_service()

            # Verify Upload Service (YouTube)
            self.orchestrator.upload_service.youtube_client.verify_service()

            logger.info("Services verification complete")
        except Exception as e:
            # Log specific error is handled in verify_service, but we log workflow failure here
            logger.error(f"Service verification failed: {e}")
            raise

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
        current_step = 1

        try:
            # Send initial status with all steps
            extra_info = f"📎 URL: {url[:50]}...\n💭 Opinion: {'Yes' if user_opinion else 'None'}"
            status_msg = await update.message.reply_text(
                self._format_progress_message(
                    current_step=1,
                    extra_info=extra_info,
                )
            )

            # Define progress callback
            async def update_status(step_message: str) -> None:
                nonlocal current_step
                if status_msg:
                    try:
                        # Parse the step from the orchestrator message
                        new_step = self._parse_step_from_message(step_message)
                        if new_step > current_step:
                            current_step = new_step
                        await status_msg.edit_text(
                            self._format_progress_message(current_step=current_step)
                        )
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
                # Show all steps completed
                total_steps = len(WORKFLOW_STEPS)
                completed_lines = ["✅ Video successfully created and uploaded!\n"]
                for step_num, step_name in WORKFLOW_STEPS.items():
                    completed_lines.append(f"✅ Step {step_num}/{total_steps}: {step_name}")
                completed_lines.extend(
                    [
                        f"\n🎬 YouTube URL: {result.youtube_url}",
                        f"📊 Processing time: {result.duration_seconds:.1f}s",
                        "\nThank you for using Reddit-to-YouTube Bot!",
                    ]
                )
                await self._send_status(update, "\n".join(completed_lines), status_msg)
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
