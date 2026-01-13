"""
Telegram bot command and message handlers.

This module defines all Telegram bot handlers for the Reddit-Flow bot.
"""

from telegram import Update
from telegram.ext import ContextTypes

from reddit_flow.config import get_logger

logger = get_logger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle the /start command.

    Sends a welcome message explaining the bot's functionality.

    Args:
        update: Telegram update object.
        context: Telegram context object.
    """
    welcome_message = (
        "🎬 Welcome to Reddit-to-YouTube Bot!\n\n"
        "I transform Reddit discussions into engaging AI-hosted videos.\n\n"
        "How to use:\n"
        "1. Find an interesting Reddit post\n"
        "2. Copy the post link\n"
        "3. Send it to me\n"
        "4. (Optional) Add your thoughts after the link\n\n"
        "Example:\n"
        "https://reddit.com/r/technology/comments/abc123/ I think this is fascinating\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - Detailed help & costs\n\n"
        "Ready when you are! Just send a Reddit link 🚀"
    )
    if update.effective_user:
        logger.info(
            "User %s (%s) started the bot", update.effective_user.id, update.effective_user.username
        )

    if update.message:
        await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle the /help command.

    Sends detailed help information including costs.

    Args:
        update: Telegram update object.
        context: Telegram context object.
    """
    if update.effective_user:
        logger.info(
            "User %s (%s) requested help", update.effective_user.id, update.effective_user.username
        )

    help_text = (
        "📖 Reddit-to-YouTube Bot Help\n\n"
        "What I Do:\n"
        "I take Reddit posts and transform them into professional "
        "AI-hosted videos, then upload them to YouTube.\n\n"
        "How to Use:\n"
        "Simply send me a Reddit post link. I support various formats:\n"
        "• https://reddit.com/r/subreddit/comments/id/\n"
        "• https://www.reddit.com/r/subreddit/comments/id/title/\n"
        "• https://old.reddit.com/r/subreddit/comments/id/\n\n"
        "Optional User Opinion:\n"
        "Add your thoughts after the link to include them in the video:\n"
        "https://reddit.com/... I disagree because...\n\n"
        "Process Steps:\n"
        "   1. Extract link from your message\n"
        "   2. Fetch Reddit post and comments\n"
        "   3. Generate script with AI\n"
        "   4. Convert to speech (ElevenLabs)\n"
        "   5. Create avatar video (HeyGen)\n"
        "   6. Upload to YouTube\n\n"
        "Tips:\n"
        "   • Use posts with good discussion\n"
        "   • Processing takes 5-10 minutes\n"
        "   • Only one operation per user at a time\n"
        "   • Check your API credits before starting\n\n"
        "Estimated Costs:\n"
        "   • ElevenLabs: ~$0.05-0.15 per video\n"
        "   • HeyGen: ~$0.10-0.50 per video\n"
        "   • Total: ~$0.15-0.65 per video"
    )
    if update.message:
        await update.message.reply_text(help_text)
