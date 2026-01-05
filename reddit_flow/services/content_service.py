"""
Content service for Reddit content extraction.

This module provides business logic for extracting and processing Reddit content,
including post data, comments, and link information parsing.
"""

import re
from typing import Any, Dict, List, Optional

from reddit_flow.clients import RedditClient
from reddit_flow.config import get_logger
from reddit_flow.exceptions import ContentError, EmptyContentError, InvalidURLError, RedditAPIError
from reddit_flow.models import LinkInfo, RedditComment, RedditPost

logger = get_logger(__name__)


class ContentService:
    """
    Service for extracting and processing Reddit content.

    This service handles:
    - Parsing Reddit URLs to extract subreddit and post ID
    - Fetching post data and comments via RedditClient
    - Validating content availability
    - Converting raw data to domain models

    Attributes:
        reddit_client: RedditClient instance for API calls.
        max_comments: Maximum number of comments to fetch.

    Example:
        >>> service = ContentService()
        >>> post = service.get_post_content("python", "abc123")
        >>> print(post.title)
    """

    # Reddit URL patterns
    REDDIT_URL_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?(?:old\.)?reddit\.com/r/(\w+)/comments/(\w+)",
        re.IGNORECASE,
    )
    REDDIT_SHORT_URL_PATTERN = re.compile(
        r"(?:https?://)?redd\.it/(\w+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        reddit_client: Optional[RedditClient] = None,
        max_comments: int = 50,
    ) -> None:
        """
        Initialize ContentService.

        Args:
            reddit_client: Optional RedditClient instance. If not provided,
                          a new client will be created.
            max_comments: Maximum number of comments to fetch per post.
        """
        self._reddit_client = reddit_client
        self._max_comments = max_comments
        logger.info(f"ContentService initialized (max_comments={max_comments})")

    @property
    def reddit_client(self) -> RedditClient:
        """Lazy-load Reddit client on first access."""
        if self._reddit_client is None:
            self._reddit_client = RedditClient()
        return self._reddit_client

    def parse_reddit_url(self, url: str) -> LinkInfo:
        """
        Parse a Reddit URL to extract subreddit and post ID.

        Supports multiple URL formats:
        - https://www.reddit.com/r/subreddit/comments/postid/...
        - https://old.reddit.com/r/subreddit/comments/postid/...
        - https://redd.it/postid

        Args:
            url: Reddit URL string.

        Returns:
            LinkInfo with subreddit and post_id.

        Raises:
            InvalidURLError: If URL cannot be parsed.
        """
        # Try standard Reddit URL pattern
        match = self.REDDIT_URL_PATTERN.search(url)
        if match:
            subreddit, post_id = match.groups()
            logger.debug(f"Parsed URL: r/{subreddit}, post={post_id}")
            return LinkInfo(
                link=url,
                subReddit=subreddit,
                postId=post_id,
            )

        # Try short URL pattern (redd.it) - not fully supported
        match = self.REDDIT_SHORT_URL_PATTERN.search(url)
        if match:
            raise InvalidURLError(
                "Short URLs (redd.it) are not supported. " "Please use the full Reddit URL."
            )

        raise InvalidURLError(f"Could not parse Reddit URL: {url}")

    def validate_url(self, subreddit: Optional[str], post_id: str) -> bool:
        """
        Validate Reddit URL components.

        Args:
            subreddit: Subreddit name (can be None for short URLs).
            post_id: Reddit post ID.

        Returns:
            True if valid, False otherwise.
        """
        # Post ID must be alphanumeric and reasonable length
        if not post_id or not re.match(r"^[a-zA-Z0-9]{2,10}$", post_id):
            return False

        # Subreddit validation (if provided)
        if subreddit and not re.match(r"^[a-zA-Z0-9_]{2,21}$", subreddit):
            return False

        return True

    def get_post_content(
        self,
        subreddit: str,
        post_id: str,
        include_comments: bool = True,
    ) -> RedditPost:
        """
        Fetch complete post content including comments.

        Args:
            subreddit: Subreddit name.
            post_id: Reddit post ID.
            include_comments: Whether to fetch comments.

        Returns:
            RedditPost model with post data.

        Raises:
            ContentError: If content cannot be extracted.
            RedditAPIError: If Reddit API call fails.
        """
        try:
            logger.info(f"Fetching content from r/{subreddit}, post={post_id}")

            # Fetch raw post data
            raw_data = self.reddit_client.get_post_data(subreddit, post_id)

            # Convert comments to models
            comments: List[RedditComment] = []
            if include_comments and raw_data.get("comments"):
                for i, comment_data in enumerate(raw_data["comments"][: self._max_comments]):
                    comment_id = comment_data.get("id", f"comment_{i}")
                    comments.append(
                        RedditComment(
                            id=comment_id,
                            author=comment_data.get("author", "[deleted]"),
                            body=comment_data.get("body", "[deleted]"),
                            score=comment_data.get("score", 0),
                        )
                    )

            # Create post model
            post = RedditPost(
                id=raw_data.get("id", post_id),
                subreddit=subreddit,
                title=raw_data.get("title", ""),
                selftext=raw_data.get("selftext", ""),
                author=raw_data.get("author", "[deleted]"),
                score=raw_data.get("score", 0),
                url=raw_data.get("url", f"https://reddit.com/r/{subreddit}/comments/{post_id}/"),
                comments=comments,
            )

            logger.info(f"Fetched post: '{post.title[:50]}...' with {len(comments)} comments")
            return post

        except RedditAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to extract content: {e}", exc_info=True)
            raise ContentError(f"Failed to extract Reddit content: {e}")

    def get_content_from_url(
        self,
        url: str,
        user_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract content from a Reddit URL with optional user commentary.

        This is the main entry point for processing user requests.

        Args:
            url: Reddit URL to process.
            user_text: Optional user commentary/opinion about the post.

        Returns:
            Dictionary with:
                - post: RedditPost model
                - link_info: LinkInfo model
                - user_text: User's commentary (if any)

        Raises:
            InvalidURLError: If URL parsing fails.
            EmptyContentError: If post has no content.
            ContentError: If content extraction fails.
        """
        # Parse URL
        link_info = self.parse_reddit_url(url)

        # Validate URL components
        if not self.validate_url(link_info.subreddit, link_info.post_id):
            raise InvalidURLError(f"Invalid Reddit URL format: {url}")

        # Fetch content
        post = self.get_post_content(link_info.subreddit, link_info.post_id)

        # Validate content exists
        if not post.selftext and not post.comments:
            raise EmptyContentError("This post has no text content or comments to convert.")

        return {
            "post": post,
            "link_info": link_info,
            "user_text": user_text,
        }

    def get_post_summary(self, post: RedditPost) -> Dict[str, Any]:
        """
        Generate a summary of the post for logging/display.

        Args:
            post: RedditPost model.

        Returns:
            Dictionary with post summary.
        """
        return {
            "id": post.id,
            "subreddit": post.subreddit,
            "title": post.title[:100] if post.title else "",
            "author": post.author,
            "score": post.score,
            "has_selftext": bool(post.selftext),
            "selftext_length": len(post.selftext) if post.selftext else 0,
            "comments_fetched": len(post.comments),
        }
