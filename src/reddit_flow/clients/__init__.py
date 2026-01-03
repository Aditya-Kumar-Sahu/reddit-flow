"""
API clients for Reddit-Flow.

This module provides client classes for interacting with external APIs:
- Reddit (PRAW)
- Google Gemini AI
- ElevenLabs TTS
- HeyGen Avatar Video
- YouTube Data API

All clients inherit from BaseClient and implement a consistent interface.
"""

from reddit_flow.clients.base import AsyncClientMixin, BaseClient, HTTPClientMixin
from reddit_flow.clients.elevenlabs_client import ElevenLabsClient
from reddit_flow.clients.gemini_client import GeminiClient
from reddit_flow.clients.heygen_client import HeyGenClient
from reddit_flow.clients.reddit_client import RedditClient

__all__ = [
    "BaseClient",
    "HTTPClientMixin",
    "AsyncClientMixin",
    "RedditClient",
    "GeminiClient",
    "ElevenLabsClient",
    "HeyGenClient",
]
