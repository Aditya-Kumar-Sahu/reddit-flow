#!/usr/bin/env python3
"""
Reddit-Flow: Transform Reddit discussions into AI-hosted YouTube videos.

This is the main entry point for the Reddit-Flow Telegram bot.
It uses the modular reddit_flow package for all functionality.

Usage:
    python main.py

Environment Variables:
    See .env.example for required configuration.
"""

import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from reddit_flow.bot import WorkflowManager, help_command, start
from reddit_flow.config import Settings, configure_logging, get_logger
from reddit_flow.exceptions import ConfigurationError

# Set up logging
configure_logging()
logger = get_logger(__name__)


def main() -> int:
    """
    Main entry point for the Reddit-Flow bot.

    Initializes all services, sets up Telegram handlers, and starts
    the bot polling loop.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        # Load and validate configuration
        logger.info("Loading configuration...")
        settings = Settings()

        # Initialize workflow manager
        logger.info("Initializing services...")
        workflow = WorkflowManager(settings=settings)

        # Verify services
        workflow.verify_services()

        # Build Telegram application
        application = (
            Application.builder().token(settings.telegram_bot_token.get_secret_value()).build()
        )

        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))

        # Add message handler for Reddit URLs
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, workflow.process_request)
        )

        logger.info("🤖 Bot is starting...")
        logger.info("Press Ctrl+C to stop")

        # Run bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)

        return 0

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n❌ Configuration Error:\n{e}\n")
        print("Please check your .env file. See .env.example for reference.")
        return 1

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        return 0

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"\n❌ Fatal Error:\n{e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
