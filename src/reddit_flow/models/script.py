"""
Script data models.

This module defines Pydantic models for AI-generated scripts,
including video scripts and their metadata.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field, field_validator


class VideoScript(BaseModel):
    """
    Model representing an AI-generated video script.

    Attributes:
        script: The full script text for the video.
        title: Generated title for the video.
        source_post_id: ID of the Reddit post used as source.
        source_subreddit: Subreddit of the source post.
        user_opinion: Optional user-provided context/opinion.
        created_at: Timestamp when the script was generated.
    """

    script: str = Field(..., description="Full script text for the video")
    title: str = Field(..., description="Generated video title")
    source_post_id: Optional[str] = Field(default=None, description="Source Reddit post ID")
    source_subreddit: Optional[str] = Field(default=None, description="Source subreddit")
    user_opinion: Optional[str] = Field(default=None, description="User-provided context")
    created_at: datetime = Field(default_factory=datetime.now, description="Generation timestamp")

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, v: str) -> str:
        """Clean and validate the title."""
        if not v:
            raise ValueError("Title cannot be empty")
        # Remove extra whitespace
        return " ".join(v.split())

    @field_validator("script", mode="before")
    @classmethod
    def clean_script(cls, v: str) -> str:
        """Clean and validate the script."""
        if not v:
            raise ValueError("Script cannot be empty")
        return v.strip()

    @computed_field
    @property
    def word_count(self) -> int:
        """Calculate the word count of the script."""
        return len(self.script.split())

    @computed_field
    @property
    def youtube_title(self) -> str:
        """Get YouTube-safe title (max 100 chars)."""
        if len(self.title) <= 100:
            return self.title
        return self.title[:97] + "..."

    @computed_field
    @property
    def estimated_duration_seconds(self) -> int:
        """Estimate video duration based on word count (avg 150 words/min)."""
        return int((self.word_count / 150) * 60)

    def validate_word_limit(self, max_words: int, allow_overflow: float = 0.2) -> bool:
        """
        Check if script is within word limit.

        Args:
            max_words: Maximum allowed words.
            allow_overflow: Percentage overflow allowed (default 20%).

        Returns:
            True if within limit (including allowed overflow).
        """
        limit_with_overflow = int(max_words * (1 + allow_overflow))
        return self.word_count <= limit_with_overflow


class ScriptGenerationRequest(BaseModel):
    """
    Model for script generation request parameters.

    Attributes:
        post_text: Main post text content.
        comments_text: Formatted comments text or JSON.
        user_opinion: Optional user context/opinion.
        max_words: Maximum word count for script.
        style: Writing style preference.
    """

    post_text: str = Field(..., description="Reddit post text content")
    comments_text: str = Field(default="", description="Formatted comments")
    user_opinion: Optional[str] = Field(default=None, description="User context")
    max_words: int = Field(default=200, ge=50, le=1000, description="Max script words")
    style: str = Field(
        default="conversational",
        description="Writing style (conversational, formal, humorous)",
    )

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        """Validate writing style."""
        valid_styles = {"conversational", "formal", "humorous", "informative"}
        if v.lower() not in valid_styles:
            raise ValueError(f"Style must be one of: {valid_styles}")
        return v.lower()
