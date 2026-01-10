"""
Reddit API client.

This module provides the client for interacting with Reddit via PRAW,
extracting posts and comments for content generation.
"""

import os
from typing import Any, Dict, List, Optional

import praw
import praw.exceptions
import praw.models
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from reddit_flow.clients.base import BaseClient
from reddit_flow.config import get_logger
from reddit_flow.exceptions import ConfigurationError, RedditAPIError
from reddit_flow.models import RedditComment, RedditPost

logger = get_logger(__name__)


class RedditClient(BaseClient):
    """
    Client for interacting with Reddit API via PRAW.

    This client handles Reddit authentication and provides methods for
    fetching posts and comments. It uses the BaseClient pattern for
    consistent initialization and health checking.

    Attributes:
        service_name: "Reddit" - identifies this service.
        reddit: The underlying PRAW Reddit instance.
        max_comments: Maximum comments to fetch per post.
        max_comment_depth: Maximum depth for comment replies.

    Example:
        >>> client = RedditClient(config={
        ...     "client_id": "...",
        ...     "client_secret": "...",
        ...     "user_agent": "...",
        ... })
        >>> post = client.get_post("technology", "abc123")
        >>> print(post.title)
    """

    service_name = "Reddit"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        max_comments: int = 50,
        max_comment_depth: int = 5,
    ) -> None:
        """
        Initialize the Reddit client.

        Args:
            config: Configuration dictionary with Reddit credentials.
                    Falls back to environment variables if not provided.
            max_comments: Maximum number of comments to fetch (default: 50).
            max_comment_depth: Maximum depth for comment replies (default: 5).
        """
        self.max_comments = max_comments
        self.max_comment_depth = max_comment_depth
        self.reddit: Optional[praw.Reddit] = None
        super().__init__(config)

    def _initialize(self) -> None:
        """
        Initialize the PRAW Reddit instance.

        Raises:
            ConfigurationError: If required credentials are missing.
            RedditAPIError: If Reddit initialization fails.
        """
        try:
            # Get credentials from config or environment
            client_id = self._config.get("client_id") or os.getenv("REDDIT_CLIENT_ID")
            client_secret = self._config.get("client_secret") or os.getenv("REDDIT_CLIENT_SECRET")
            user_agent = self._config.get("user_agent") or os.getenv("REDDIT_USER_AGENT")
            username = self._config.get("username") or os.getenv("REDDIT_USERNAME")
            password = self._config.get("password") or os.getenv("REDDIT_PASSWORD")

            # Validate required credentials
            if not all([client_id, client_secret, user_agent]):
                missing = []
                if not client_id:
                    missing.append("client_id/REDDIT_CLIENT_ID")
                if not client_secret:
                    missing.append("client_secret/REDDIT_CLIENT_SECRET")
                if not user_agent:
                    missing.append("user_agent/REDDIT_USER_AGENT")
                raise ConfigurationError(
                    "Missing Reddit credentials",
                    details={"missing": missing},
                )

            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
                username=username,
                password=password,
            )
            logger.debug("PRAW Reddit instance created")

        except ConfigurationError:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise RedditAPIError(
                f"Reddit initialization failed: {e}",
                details={"error_type": type(e).__name__},
            )

    def _health_check(self) -> bool:
        """
        Verify Reddit API connectivity.

        Returns:
            True if Reddit is accessible.

        Raises:
            RedditAPIError: If the health check fails.
        """
        try:
            # Simple check - try to access a known subreddit
            if self.reddit is None:
                raise RedditAPIError("Reddit client not initialized")
            self.reddit.subreddit("test").id
            return True
        except Exception as e:
            logger.error(f"Reddit health check failed: {e}")
            raise RedditAPIError(
                "Reddit health check failed",
                details={"error": str(e)},
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(praw.exceptions.PRAWException),
    )
    def get_post(self, subreddit_name: str, post_id: str) -> RedditPost:
        """
        Fetch a Reddit post with comments.

        Args:
            subreddit_name: Name of the subreddit (without r/ prefix).
            post_id: Reddit post ID.

        Returns:
            RedditPost model with post data and comments.

        Raises:
            RedditAPIError: If fetching the post fails.
        """
        try:
            logger.info(f"Fetching post r/{subreddit_name}/{post_id}")
            if self.reddit is None:
                raise RedditAPIError("Reddit client not initialized")
            submission = self.reddit.submission(id=post_id)

            # Load comment replies (limited to avoid excessive API calls)
            submission.comments.replace_more(limit=5)

            # Extract comments
            comments = self._extract_comments(submission.comments.list()[: self.max_comments])

            # Build RedditPost model
            post = RedditPost(
                id=post_id,
                subreddit=subreddit_name,
                title=submission.title,
                selftext=submission.selftext or "",
                url=submission.url,
                author=str(submission.author) if submission.author else "[deleted]",
                score=submission.score,
                comments=comments,
            )

            logger.info(f"Fetched post with {len(comments)} comments")
            return post

        except praw.exceptions.InvalidURL:
            raise RedditAPIError(
                "Invalid Reddit post URL",
                details={"subreddit": subreddit_name, "post_id": post_id},
            )
        except RedditAPIError:
            raise
        except Exception as e:
            logger.error(f"Error fetching Reddit post: {e}", exc_info=True)
            raise RedditAPIError(
                f"Failed to fetch Reddit post: {e}",
                details={"subreddit": subreddit_name, "post_id": post_id},
            )

    def get_post_data(self, subreddit_name: str, post_id: str) -> Dict[str, Any]:
        """
        Fetch Reddit post data as a dictionary.

        This method provides backward compatibility with the original API.
        For new code, prefer using get_post() which returns a typed model.

        Args:
            subreddit_name: Name of the subreddit.
            post_id: Reddit post ID.

        Returns:
            Dictionary containing post data and comments.

        Raises:
            RedditAPIError: If fetching post data fails.
        """
        post = self.get_post(subreddit_name, post_id)
        return {
            "title": post.title,
            "selftext": post.selftext,
            "url": post.url,
            "author": post.author,
            "score": post.score,
            "comments": [
                {
                    "id": c.id,
                    "body": c.body,
                    "author": c.author,
                    "depth": c.depth,
                    "score": c.score,
                }
                for c in post.comments
            ],
        }

    def _extract_comments(
        self,
        comments: List,
        depth: int = 0,
    ) -> List[RedditComment]:
        """
        Extract comment data recursively with depth limiting.

        Args:
            comments: List of PRAW comment objects.
            depth: Current recursion depth.

        Returns:
            List of RedditComment models.
        """
        all_comments: List[RedditComment] = []

        if depth > self.max_comment_depth:
            return all_comments

        for comment in comments:
            # Skip "MoreComments" placeholder objects
            if isinstance(comment, praw.models.MoreComments):
                continue

            try:
                reddit_comment = RedditComment(
                    id=comment.id,
                    body=comment.body,
                    author=str(comment.author) if comment.author else "[deleted]",
                    depth=depth,
                    score=comment.score,
                )
                all_comments.append(reddit_comment)

                # Recursively extract replies
                if hasattr(comment, "replies") and len(comment.replies) > 0:
                    reply_list = comment.replies.list()[:10]  # Limit replies per comment
                    all_comments.extend(self._extract_comments(reply_list, depth + 1))

            except Exception as e:
                comment_id = getattr(comment, "id", "unknown")
                logger.warning(f"Error extracting comment {comment_id}: {e}")
                continue

        return all_comments
