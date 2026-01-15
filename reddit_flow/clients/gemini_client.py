"""
Gemini AI client for content extraction and script generation.

This module provides a client for interacting with Google's Gemini AI API,
handling link extraction and video script generation from Reddit content.
"""

import json
import os
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from reddit_flow.clients.base import BaseClient
from reddit_flow.config import get_logger
from reddit_flow.exceptions import AIGenerationError, ConfigurationError
from reddit_flow.models import LinkInfo, VideoScript

logger = get_logger(__name__)


class GeminiClient(BaseClient):
    """
    Client for Google Gemini AI operations.

    This client handles:
    - Extracting Reddit link information from user messages
    - Generating video scripts from Reddit post content

    Attributes:
        service_name: Name of the service for logging/identification.
        model: The Gemini GenerativeModel instance.

    Example:
        >>> client = GeminiClient(config={"api_key": "your-key"})
        >>> # Or using environment variables
        >>> client = GeminiClient()
        >>> link_info = await client.extract_link_info("Check this https://reddit.com/r/...")
    """

    service_name = "Gemini"

    # Default configuration values
    DEFAULT_MODEL = "gemini-2.5-flash-lite"
    DEFAULT_MAX_WORDS = 500
    DEFAULT_MAX_COMMENTS = 50

    def _initialize(self) -> None:
        """
        Initialize the Gemini client.

        Configures the Google Generative AI SDK and creates a model instance.

        Raises:
            ConfigurationError: If API key is missing.
            AIGenerationError: If SDK initialization fails.
        """
        # Get API key from config or environment
        api_key = self._config.get("api_key") or os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise ConfigurationError(
                "Gemini API key not found",
                details={"required": "GOOGLE_API_KEY environment variable or api_key in config"},
            )

        # Get model name from config or use default
        model_name = self._config.get("model", self.DEFAULT_MODEL)

        # Get script settings from config
        self._max_words = self._config.get("max_words", self.DEFAULT_MAX_WORDS)
        self._max_comments = self._config.get("max_comments", self.DEFAULT_MAX_COMMENTS)

        try:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(model_name)
            logger.info(
                "Gemini client initialized",
                extra={"model": model_name, "max_words": self._max_words},
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise AIGenerationError(f"Gemini initialization failed: {e}")

    def _health_check(self) -> bool:
        """
        Verify the Gemini API is accessible.

        Performs a minimal test generation to verify connectivity.

        Returns:
            True if the API is accessible and working.
        """
        try:
            # Minimal test to verify the model is accessible
            response = self._model.generate_content("Say 'ok'")
            return response.text is not None
        except Exception as e:
            logger.warning(f"Gemini health check failed: {e}")
            return False

    @property
    def model(self) -> genai.GenerativeModel:
        """Get the underlying Gemini model instance."""
        return self._model

    @property
    def max_words(self) -> int:
        """Get the configured maximum script word count."""
        return self._max_words

    @property
    def max_comments(self) -> int:
        """Get the configured maximum comments to include."""
        return self._max_comments

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def extract_link_info(self, message_text: str) -> LinkInfo:
        """
        Extract Reddit link information from user message.

        Uses Gemini AI to parse a user message and extract the Reddit URL,
        subreddit name, post ID, and any additional user text.

        Args:
            message_text: Raw message text from user containing a Reddit link.

        Returns:
            LinkInfo model with extracted information.

        Raises:
            AIGenerationError: If extraction or parsing fails.

        Example:
            >>> info = await client.extract_link_info(
            ...     "Check this out https://reddit.com/r/Python/comments/abc123/"
            ... )
            >>> print(info.subreddit)
            'Python'
        """
        try:
            prompt = self._build_link_extraction_prompt(message_text)

            logger.debug("Extracting link info with Gemini")
            response = await self._model.generate_content_async(prompt)
            text = response.text.strip()

            # Clean up markdown code blocks if present
            text = self._clean_json_response(text)

            result = json.loads(text)

            # Validate required fields
            required_fields = ["link", "subReddit", "postId"]
            if not all(key in result for key in required_fields):
                missing = [k for k in required_fields if k not in result]
                raise ValueError(f"Missing required fields in AI response: {missing}")

            # Parse into LinkInfo model (handles alias mapping)
            link_info = LinkInfo.model_validate(result)

            logger.info(f"Extracted link info for r/{link_info.subreddit}/{link_info.post_id}")
            return link_info

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {text}")
            raise AIGenerationError(f"Invalid JSON from AI: {e}")
        except ValueError as e:
            logger.error(f"Validation error in AI response: {e}")
            raise AIGenerationError(f"Invalid AI response: {e}")
        except Exception as e:
            logger.error(f"Error extracting link info: {e}", exc_info=True)
            raise AIGenerationError(f"Failed to extract link information: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def generate_script(
        self,
        post_text: str,
        comments_data: List[Dict[str, Any]],
        user_opinion: Optional[str] = None,
        source_post_id: Optional[str] = None,
        source_subreddit: Optional[str] = None,
    ) -> VideoScript:
        """
        Generate video script from Reddit content.

        Uses Gemini AI to create an engaging video script based on a Reddit
        post and its comments.

        Args:
            post_text: Main post text content.
            comments_data: List of comment dictionaries with body, author, score.
            user_opinion: Optional user-provided context or opinion.
            source_post_id: Optional Reddit post ID for tracking.
            source_subreddit: Optional subreddit name for tracking.

        Returns:
            VideoScript model with generated script and title.

        Raises:
            AIGenerationError: If script generation or parsing fails.

        Example:
            >>> script = await client.generate_script(
            ...     post_text="This is amazing...",
            ...     comments_data=[{"body": "Agreed!", "score": 100}],
            ... )
            >>> print(script.word_count)
        """
        try:
            # Limit comments to avoid token limits
            limited_comments = comments_data[: self._max_comments]

            prompt = self._build_script_generation_prompt(post_text, limited_comments, user_opinion)

            logger.debug("Generating script with Gemini")
            response = await self._model.generate_content_async(prompt)
            text = response.text.strip()

            text = self._clean_json_response(text)
            result = json.loads(text)

            # Validate response structure
            if "script" not in result or "title" not in result:
                raise ValueError("Missing script or title in AI response")

            # Create VideoScript model
            video_script = VideoScript(
                script=result["script"],
                title=result["title"],
                source_post_id=source_post_id,
                source_subreddit=source_subreddit,
                user_opinion=user_opinion,
            )

            # Log warning if script exceeds word limit
            if not video_script.validate_word_limit(self._max_words):
                logger.warning(f"Script length ({video_script.word_count} words) exceeds limit")

            logger.info(
                f"Generated script: {video_script.word_count} words, "
                f"title: {video_script.title[:50]}..."
            )
            return video_script

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {text}")
            raise AIGenerationError(f"Invalid JSON from AI: {e}")
        except ValueError as e:
            logger.error(f"Validation error in AI response: {e}")
            raise AIGenerationError(f"Invalid AI response: {e}")
        except Exception as e:
            logger.error(f"Error generating script: {e}", exc_info=True)
            raise AIGenerationError(f"Failed to generate script: {e}")

    async def generate_script_dict(
        self,
        post_text: str,
        comments_data: List[Dict[str, Any]],
        user_opinion: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Generate video script and return as dictionary.

        This is a backward-compatible method that returns the raw dictionary
        format used by the original implementation.

        Args:
            post_text: Main post text content.
            comments_data: List of comment dictionaries.
            user_opinion: Optional user-provided context.

        Returns:
            Dictionary with 'script' and 'title' keys.

        Raises:
            AIGenerationError: If script generation fails.
        """
        script = await self.generate_script(post_text, comments_data, user_opinion)
        return {
            "script": script.script,
            "title": script.title,
        }

    async def extract_link_info_dict(self, message_text: str) -> Dict[str, str]:
        """
        Extract link info and return as dictionary.

        This is a backward-compatible method that returns the raw dictionary
        format used by the original implementation.

        Args:
            message_text: Raw message text from user.

        Returns:
            Dictionary with link, subReddit, postId, and text keys.

        Raises:
            AIGenerationError: If extraction fails.
        """
        link_info = await self.extract_link_info(message_text)
        return {
            "link": link_info.link,
            "subReddit": link_info.subreddit,
            "postId": link_info.post_id,
            "text": link_info.user_text or "",
        }

    def _build_link_extraction_prompt(self, message_text: str) -> str:
        """
        Build the prompt for link extraction.

        Args:
            message_text: The user's message containing a Reddit link.

        Returns:
            Formatted prompt string for the AI model.
        """
        return f"""
Extract the Reddit link, subreddit, post ID, and any additional user text from this message:
"{message_text}"

Return JSON with keys: link, subReddit, postId, text.
If no additional text is provided, set 'text' to null.
Example JSON format:
{{
    "link": "https://www.reddit.com/r/sheffield/comments/1nf7kh6/guys_the_impossible_happened/",
    "subReddit": "sheffield",
    "postId": "1nf7kh6",
    "text": "text provided by the user other than the link, this can be null"
}}
"""

    def _build_script_generation_prompt(
        self,
        post_text: str,
        comments: List[Dict[str, Any]],
        user_opinion: Optional[str],
    ) -> str:
        """
        Build the prompt for script generation.

        Args:
            post_text: The Reddit post text.
            comments: List of comment dictionaries.
            user_opinion: Optional user context.

        Returns:
            Formatted prompt string for the AI model.
        """
        comments_str = json.dumps(comments, indent=2)

        system_prompt = f"""
You are an expert script writer for social media content.

## Writing Instructions:
Write a script for a short-form video for a broad audience.
Do not use emojis in the script, and avoid Gen Z slang.
The script should be less than {self._max_words} words with an engaging hook and interactive CTA.

Write like a confident, clear-thinking human speaking to another smart human.
Avoid robotic phrases like 'in today's fast-paced world', 'leveraging synergies', or 'furthermore'.
Skip unnecessary dashes (—), quotation marks (""), and corporate buzzwords like 'cutting-edge',
'robust', or 'seamless experience'.

No AI tone. No fluff. No filler.
Use natural transitions like 'here's the thing', 'let's break it down',
or 'what this really means is...'
Keep sentences varied in length and rhythm, like how real people speak or write.
Prioritize clarity, personality, and usefulness.
Every sentence should feel intentional, not generated.
Do not ask questions and then answer them yourself.
Do not describe scenes, just write the speaking script without any markdown.
"""

        user_prompt = f"""
Post Content: {post_text}

Comments: {comments_str}

User Opinion: {user_opinion or 'None provided'}

Generate a video script and title based on this Reddit content.
Return JSON with keys: 'script' and 'title'.
"""

        return f"{system_prompt}\n\n{user_prompt}"

    @staticmethod
    def _clean_json_response(text: str) -> str:
        """
        Remove markdown code blocks from JSON response.

        Args:
            text: Raw response text that may contain markdown formatting.

        Returns:
            Cleaned JSON string without markdown code blocks.
        """
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
        return text.strip()
