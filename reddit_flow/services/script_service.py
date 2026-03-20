"""
Script service for AI content generation.

This module provides business logic for generating video scripts from Reddit content
using the Gemini AI client.
"""

from typing import Any, Dict, List, Optional

from reddit_flow.clients import GeminiClient
from reddit_flow.config import Settings, get_logger
from reddit_flow.exceptions import AIGenerationError, ContentError
from reddit_flow.models import ContentItem, RedditComment, RedditPost, ScriptBrief, VideoScript
from reddit_flow.models.pipeline import PipelineRequest
from reddit_flow.pipeline.contracts import ScriptProvider
from reddit_flow.pipeline.providers import GeminiScriptProvider
from reddit_flow.pipeline.registry import ProviderRegistry

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
        settings: Optional[Settings] = None,
        script_provider_registry: Optional[ProviderRegistry[ScriptProvider]] = None,
    ) -> None:
        """
        Initialize ScriptService.

        Args:
            gemini_client: Optional GeminiClient instance. If not provided,
                          a new client will be created when needed.
            max_words: Maximum word count for generated scripts.
            max_comments: Maximum number of comments to include in context.
            settings: Optional Settings instance.
            script_provider_registry: Optional registry for provider fallback resolution.
        """
        self._gemini_client = gemini_client
        self._max_words = max_words
        self._max_comments = max_comments
        self.settings = settings or Settings()
        self._script_provider_registry = script_provider_registry
        logger.info(
            f"ScriptService initialized (max_words={max_words}, max_comments={max_comments})"
        )

    @property
    def gemini_client(self) -> GeminiClient:
        """Lazy-load Gemini client on first access."""
        if self._gemini_client is None:
            self._gemini_client = GeminiClient()
        return self._gemini_client

    def build_script_brief(
        self,
        content_item: ContentItem,
        target: str = "youtube_video",
    ) -> ScriptBrief:
        """Build a target-specific brief for script generation."""
        normalized_target = target.strip().lower()

        if normalized_target == "instagram_reel":
            return ScriptBrief(
                target=normalized_target,
                max_words=min(self._max_words, 180),
                hook_required=True,
                cta_required=True,
                aspect_ratio="9:16",
                caption_style="short",
                audience_notes=content_item.summary or content_item.title,
            )

        if normalized_target == "messaging_summary":
            return ScriptBrief(
                target=normalized_target,
                max_words=min(self._max_words, 120),
                hook_required=True,
                cta_required=False,
                aspect_ratio="text",
                caption_style="summary",
                audience_notes=content_item.summary or content_item.title,
            )

        return ScriptBrief(
            target=normalized_target,
            max_words=min(self._max_words, 250),
            hook_required=True,
            cta_required=True,
            aspect_ratio="16:9",
            caption_style="standard",
            audience_notes=content_item.summary or content_item.title,
        )

    def _resolve_script_provider(self) -> ScriptProvider:
        """Resolve the configured script provider, falling back to Gemini."""
        if self._script_provider_registry is None:
            return GeminiScriptProvider(self.gemini_client)

        preferred = self.settings.default_script_provider
        fallbacks = (
            self.settings.script_provider_fallbacks
            if self.settings.enable_provider_fallbacks
            else []
        )
        try:
            return self._script_provider_registry.resolve(preferred=preferred, fallbacks=fallbacks)
        except LookupError:
            if preferred != "gemini":
                try:
                    return self._script_provider_registry.resolve(preferred="gemini")
                except LookupError:
                    pass
            return GeminiScriptProvider(self.gemini_client)

    def resolve_script_provider_name(self) -> str:
        """Resolve the active script provider name for logging and tracing."""
        try:
            return self._resolve_script_provider().provider_name
        except Exception:
            return str(getattr(self.settings, "default_script_provider", "gemini"))

    def _build_provider_candidates(self) -> List[ScriptProvider]:
        """Build the ordered provider chain for runtime fallback."""
        if self._script_provider_registry is None:
            return [GeminiScriptProvider(self.gemini_client)]

        candidates: List[ScriptProvider] = []
        candidate_names: List[str] = []

        preferred = str(getattr(self.settings, "default_script_provider", "gemini")).strip().lower()
        if preferred:
            candidate_names.append(preferred)

        if getattr(self.settings, "enable_provider_fallbacks", False):
            for fallback in getattr(self.settings, "script_provider_fallbacks", []):
                name = str(fallback).strip().lower()
                if name and name not in candidate_names:
                    candidate_names.append(name)

        if "gemini" not in candidate_names:
            candidate_names.append("gemini")

        for candidate_name in candidate_names:
            if candidate_name == "gemini" and self._script_provider_registry is None:
                candidates.append(GeminiScriptProvider(self.gemini_client))
                continue
            try:
                candidates.append(self._script_provider_registry.get(candidate_name))
            except LookupError:
                if candidate_name == "gemini":
                    candidates.append(GeminiScriptProvider(self.gemini_client))

        if not candidates:
            candidates.append(GeminiScriptProvider(self.gemini_client))

        return candidates

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
        if self.settings.env != "prod":
            logger.info(f"Skipping AI script generation in {self.settings.env} mode")
            return VideoScript(
                title=f"TEST: {post.title}",
                script="This is a test script generated in test mode. " * 5,
                source_post_id=post.id,
                source_subreddit=post.subreddit,
                user_opinion=user_opinion,
            )

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

    async def generate_script_from_content_item(
        self,
        content_item: ContentItem,
        user_opinion: Optional[str] = None,
        target: str = "youtube_video",
    ) -> VideoScript:
        """
        Generate a video script from a canonical content item.

        This enables the generic pipeline to handle non-Reddit sources such as
        Medium while reusing the existing Gemini-based script generation path.
        """
        if self.settings.env != "prod":
            logger.info(f"Skipping AI script generation in {self.settings.env} mode")
            return VideoScript(
                title=f"TEST: {content_item.title}",
                script="This is a test script generated in test mode. " * 5,
                source_post_id=content_item.source_id,
                source_subreddit=content_item.source_type,
                user_opinion=user_opinion,
            )

        try:
            post_text = content_item.text_content
            if not post_text.strip():
                raise ContentError("Content item has no content to generate script from")

            comments_data = self._format_generic_comments(content_item.comments)
            script_brief = self.build_script_brief(content_item, target=target)
            request = PipelineRequest(
                source_url=content_item.source_url,
                source_type=content_item.source_type,
                user_input=user_opinion,
                metadata={
                    "target": script_brief.target,
                    "script_brief": script_brief.model_dump(),
                },
            )

            logger.info(
                "Generating script for canonical content '%s' (%s)",
                content_item.source_id,
                content_item.source_type,
            )

            for provider in self._build_provider_candidates():
                if not hasattr(provider, "generate_script"):
                    continue
                try:
                    script = await provider.generate_script(content_item, request)
                except AIGenerationError as exc:
                    logger.warning(
                        "Script provider '%s' failed for content '%s': %s",
                        provider.provider_name,
                        content_item.source_id,
                        exc,
                    )
                    continue
                except Exception as exc:
                    logger.warning(
                        "Unexpected script-provider failure from '%s' for '%s': %s",
                        provider.provider_name,
                        content_item.source_id,
                        exc,
                    )
                    continue

                if isinstance(script, VideoScript):
                    return script

            return await self.gemini_client.generate_script(
                post_text=post_text,
                comments_data=comments_data,
                user_opinion=user_opinion,
                source_post_id=content_item.source_id,
                source_subreddit=content_item.source_type,
            )

        except AIGenerationError:
            raise
        except ContentError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate script from content item: {e}", exc_info=True)
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

    def _format_generic_comments(
        self,
        comments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Format canonical comments for AI script generation.

        Args:
            comments: Canonical comments where each item is a dictionary.

        Returns:
            List of simplified comment dictionaries for the AI provider.
        """
        formatted = []

        for comment in comments[: self._max_comments]:
            body = str(comment.get("body", "")).strip()
            if not body or body == "[deleted]":
                continue

            formatted.append(
                {
                    "body": body,
                    "author": str(comment.get("author", "[deleted]")),
                    "score": int(comment.get("score", 0) or 0),
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
