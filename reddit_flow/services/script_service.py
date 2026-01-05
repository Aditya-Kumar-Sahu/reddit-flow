"""
Script service for AI content generation.

This module provides business logic for generating video scripts from Reddit content
using the Gemini AI client.
"""

from typing import Any, Dict, List, Optional

from reddit_flow.clients import GeminiClient
from reddit_flow.config import get_logger
from reddit_flow.exceptions import AIGenerationError, ContentError
from reddit_flow.models import RedditComment, RedditPost, VideoScript

logger = get_logger(__name__)


class ScriptService:
    """
    Service for generating video scripts from Reddit content.

    This service handles:
    - Converting RedditPost models to script-ready format
    - Orchestrating the GeminiClient for AI generation
    - Formatting comments for optimal script context
    - Validating generated scripts

    Attributes:
        gemini_client: GeminiClient instance for AI generation.
        max_words: Maximum word count for generated scripts.
        max_comments: Maximum number of comments to include.

    Example:
        >>> service = ScriptService()
        >>> post = RedditPost(id="abc123", subreddit="python", ...)
        >>> script = await service.generate_script(post)
        >>> print(script.title)
    """

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        max_words: int = 250,
        max_comments: int = 10,
    ) -> None:
        """
        Initialize ScriptService.

        Args:
            gemini_client: Optional GeminiClient instance. If not provided,
                          a new client will be created when needed.
            max_words: Maximum word count for generated scripts.
            max_comments: Maximum number of comments to include in context.
        """
        self._gemini_client = gemini_client
        self._max_words = max_words
        self._max_comments = max_comments
        logger.info(
            f"ScriptService initialized (max_words={max_words}, max_comments={max_comments})"
        )

    @property
    def gemini_client(self) -> GeminiClient:
        """Lazy-load Gemini client on first access."""
        if self._gemini_client is None:
            self._gemini_client = GeminiClient()
        return self._gemini_client

    async def generate_script(
        self,
        post: RedditPost,
        user_opinion: Optional[str] = None,
    ) -> VideoScript:
        """
        Generate a video script from a Reddit post.

        Converts the RedditPost model to the format expected by GeminiClient
        and generates a script using AI.

        Args:
            post: RedditPost model with content and comments.
            user_opinion: Optional user context or opinion to include.

        Returns:
            VideoScript model with generated script and title.

        Raises:
            AIGenerationError: If script generation fails.
            ContentError: If post content is invalid.
        """
        try:
            # Validate post has content
            post_text = self._build_post_text(post)
            if not post_text.strip():
                raise ContentError("Post has no content to generate script from")

            # Format comments for AI context
            comments_data = self._format_comments(post.comments)

            logger.info(
                f"Generating script for post '{post.id}' from r/{post.subreddit} "
                f"({len(comments_data)} comments)"
            )

            # Generate script using Gemini
            script = await self.gemini_client.generate_script(
                post_text=post_text,
                comments_data=comments_data,
                user_opinion=user_opinion,
                source_post_id=post.id,
                source_subreddit=post.subreddit,
            )

            logger.info(
                f"Generated script: {script.word_count} words, " f"title: '{script.title[:50]}...'"
            )

            return script

        except AIGenerationError:
            raise
        except ContentError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate script: {e}", exc_info=True)
            raise AIGenerationError(f"Script generation failed: {e}")

    async def generate_script_from_dict(
        self,
        content: Dict[str, Any],
        user_opinion: Optional[str] = None,
    ) -> VideoScript:
        """
        Generate a video script from a dictionary of content.

        This method supports the legacy dictionary format used in the original
        main.py implementation for backward compatibility.

        Args:
            content: Dictionary with 'post' and optional 'comments' keys.
                    - post: Dict with 'title', 'selftext', 'author', etc.
                    - comments: List of comment dicts with 'body', 'author', 'score'.
            user_opinion: Optional user context or opinion.

        Returns:
            VideoScript model with generated script and title.

        Raises:
            AIGenerationError: If script generation fails.
            ContentError: If content format is invalid.
        """
        try:
            # Extract post data
            post_data = content.get("post", {})
            post_id = post_data.get("id", "unknown")
            subreddit = content.get("subreddit", post_data.get("subreddit", "unknown"))

            # Build post text from dictionary
            title = post_data.get("title", "")
            selftext = post_data.get("selftext", "")
            post_text = f"{title}\n\n{selftext}".strip()

            if not post_text:
                raise ContentError("Content dictionary has no post text")

            # Format comments from dictionary
            raw_comments = content.get("comments", [])
            comments_data = [
                {
                    "body": c.get("body", ""),
                    "author": c.get("author", "[deleted]"),
                    "score": c.get("score", 0),
                }
                for c in raw_comments[: self._max_comments]
                if c.get("body")
            ]

            logger.info(
                f"Generating script from dict for post '{post_id}' "
                f"({len(comments_data)} comments)"
            )

            # Generate script
            script = await self.gemini_client.generate_script(
                post_text=post_text,
                comments_data=comments_data,
                user_opinion=user_opinion,
                source_post_id=post_id,
                source_subreddit=subreddit,
            )

            return script

        except AIGenerationError:
            raise
        except ContentError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate script from dict: {e}", exc_info=True)
            raise AIGenerationError(f"Script generation failed: {e}")

    def _build_post_text(self, post: RedditPost) -> str:
        """
        Build the post text content for script generation.

        Combines the post title and body text in a format suitable for
        AI script generation.

        Args:
            post: RedditPost model.

        Returns:
            Combined post text string.
        """
        parts = []

        if post.title:
            parts.append(post.title)

        if post.selftext:
            parts.append(post.selftext)

        return "\n\n".join(parts)

    def _format_comments(
        self,
        comments: List[RedditComment],
    ) -> List[Dict[str, Any]]:
        """
        Format comments for AI script generation.

        Converts RedditComment models to dictionary format expected by
        GeminiClient, limiting to max_comments and filtering out deleted.

        Args:
            comments: List of RedditComment models.

        Returns:
            List of comment dictionaries with body, author, and score.
        """
        formatted = []

        for comment in comments[: self._max_comments]:
            # Skip deleted comments
            if comment.body == "[deleted]":
                continue

            formatted.append(
                {
                    "body": comment.body,
                    "author": comment.author,
                    "score": comment.score,
                }
            )

        return formatted

    def _validate_script(self, script: VideoScript) -> bool:
        """
        Validate a generated script.

        Checks that the script meets minimum quality requirements.

        Args:
            script: VideoScript to validate.

        Returns:
            True if script is valid, False otherwise.
        """
        # Must have content
        if not script.script or not script.script.strip():
            return False

        # Must have a title
        if not script.title or not script.title.strip():
            return False

        # Should have reasonable length
        if script.word_count < 10:
            return False

        return True
