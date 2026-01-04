"""
Reddit data models.

This module defines Pydantic models for Reddit-related data structures,
including posts, comments, and extracted link information.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class RedditComment(BaseModel):
    """
    Model representing a Reddit comment.

    Attributes:
        id: Unique Reddit comment ID.
        body: The text content of the comment.
        author: Username of the comment author.
        depth: Nesting depth in the comment thread (0 = top-level).
        score: Net upvotes on the comment.
    """

    id: str = Field(..., description="Unique Reddit comment ID")
    body: str = Field(..., description="Comment text content")
    author: str = Field(default="[deleted]", description="Comment author username")
    depth: int = Field(default=0, ge=0, description="Comment nesting depth")
    score: int = Field(default=0, description="Net upvote score")

    @field_validator("author", mode="before")
    @classmethod
    def handle_deleted_author(cls, v: Optional[str]) -> str:
        """Handle None or empty author (deleted users)."""
        if v is None or v == "" or v == "None":
            return "[deleted]"
        return str(v)

    @field_validator("body", mode="before")
    @classmethod
    def handle_deleted_body(cls, v: Optional[str]) -> str:
        """Handle None or empty body (deleted comments)."""
        if v is None or v == "":
            return "[deleted]"
        return str(v)


class RedditPost(BaseModel):
    """
    Model representing a Reddit post/submission.

    Attributes:
        id: Unique Reddit post ID.
        subreddit: Name of the subreddit (without r/ prefix).
        title: Post title.
        selftext: Post body text (empty for link posts).
        url: URL of the post or linked content.
        author: Username of the post author.
        score: Net upvotes on the post.
        comments: List of top-level and nested comments.
        created_utc: UTC timestamp when the post was created.
    """

    id: str = Field(..., description="Unique Reddit post ID")
    subreddit: str = Field(..., description="Subreddit name without r/ prefix")
    title: str = Field(..., description="Post title")
    selftext: str = Field(default="", description="Post body text")
    url: str = Field(..., description="Post or linked content URL")
    author: str = Field(default="[deleted]", description="Post author username")
    score: int = Field(default=0, description="Net upvote score")
    comments: List[RedditComment] = Field(default_factory=list, description="Post comments")
    created_utc: Optional[datetime] = Field(default=None, description="Post creation time")

    @field_validator("author", mode="before")
    @classmethod
    def handle_deleted_author(cls, v: Optional[str]) -> str:
        """Handle None or empty author (deleted users)."""
        if v is None or v == "" or v == "None":
            return "[deleted]"
        return str(v)

    @property
    def permalink(self) -> str:
        """Generate Reddit permalink for this post."""
        return f"https://www.reddit.com/r/{self.subreddit}/comments/{self.id}/"

    @property
    def comment_count(self) -> int:
        """Return total number of comments."""
        return len(self.comments)

    def get_top_comments(self, limit: int = 10, min_score: int = 0) -> List[RedditComment]:
        """
        Get top comments by score.

        Args:
            limit: Maximum number of comments to return.
            min_score: Minimum score threshold.

        Returns:
            List of top comments sorted by score descending.
        """
        filtered = [c for c in self.comments if c.score >= min_score]
        return sorted(filtered, key=lambda c: c.score, reverse=True)[:limit]


class LinkInfo(BaseModel):
    """
    Model for extracted Reddit link information from user messages.

    This model is used to parse AI-extracted information from user messages
    containing Reddit links.

    Attributes:
        link: Full Reddit post URL.
        subReddit: Extracted subreddit name.
        postId: Extracted Reddit post ID.
        user_text: Optional additional text from the user.
    """

    link: str = Field(..., description="Full Reddit post URL")
    subreddit: str = Field(..., alias="subReddit", description="Subreddit name")
    post_id: str = Field(..., alias="postId", description="Reddit post ID")
    user_text: Optional[str] = Field(
        default=None, alias="text", description="Additional user-provided text"
    )

    model_config = {
        "populate_by_name": True,  # Allow both alias and field name
        "str_strip_whitespace": True,
    }

    @field_validator("link", mode="before")
    @classmethod
    def validate_reddit_link(cls, v: str) -> str:
        """Validate that the link is a Reddit URL."""
        if v and "reddit.com" not in v.lower():
            raise ValueError("Link must be a Reddit URL")
        return v

    @field_validator("subreddit", mode="before")
    @classmethod
    def clean_subreddit(cls, v: str) -> str:
        """Remove r/ prefix if present."""
        if v and v.startswith("r/"):
            return v[2:]
        return v
