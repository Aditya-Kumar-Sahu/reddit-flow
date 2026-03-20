"""Compatibility wrapper for the Telegram workflow entrypoint."""

from reddit_flow.channels.telegram_channel import TelegramChannel, WorkflowManager

WORKFLOW_STEPS = {
    1: "Parsing URL",
    2: "Fetching Reddit content",
    3: "Generating AI script",
    4: "Generating audio",
    5: "Generating video",
    6: "Uploading to YouTube",
}

__all__ = ["TelegramChannel", "WorkflowManager", "WORKFLOW_STEPS"]
