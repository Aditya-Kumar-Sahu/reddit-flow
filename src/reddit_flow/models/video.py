"""
Video data models.

This module defines Pydantic models for video generation and upload,
including HeyGen video generation and YouTube upload metadata.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field, field_validator


class VideoStatus(str, Enum):
    """Enumeration of possible video generation statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoDimension(BaseModel):
    """
    Model for video dimensions.

    Attributes:
        width: Video width in pixels.
        height: Video height in pixels.
    """

    width: int = Field(default=1080, ge=100, le=4096, description="Video width in pixels")
    height: int = Field(default=1920, ge=100, le=4096, description="Video height in pixels")

    @computed_field
    @property
    def aspect_ratio(self) -> str:
        """Calculate aspect ratio as a string (e.g., '9:16')."""
        from math import gcd

        divisor = gcd(self.width, self.height)
        w = self.width // divisor
        h = self.height // divisor
        return f"{w}:{h}"

    @computed_field
    @property
    def is_portrait(self) -> bool:
        """Check if video is portrait orientation."""
        return self.height > self.width

    @computed_field
    @property
    def is_landscape(self) -> bool:
        """Check if video is landscape orientation."""
        return self.width > self.height


class AudioAsset(BaseModel):
    """
    Model for uploaded audio assets.

    Attributes:
        url: URL of the uploaded audio file.
        asset_id: Optional asset ID from the service.
        duration_seconds: Audio duration in seconds.
        file_size_bytes: File size in bytes.
    """

    url: str = Field(..., description="URL of uploaded audio")
    asset_id: Optional[str] = Field(default=None, description="Service asset ID")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration")
    file_size_bytes: Optional[int] = Field(default=None, description="File size in bytes")


class VideoGenerationRequest(BaseModel):
    """
    Model for HeyGen video generation request.

    Attributes:
        audio_url: URL of the audio file to use.
        avatar_id: HeyGen avatar ID.
        avatar_style: Avatar style (normal, circle, etc.).
        title: Optional video title.
        dimension: Video dimensions.
        test_mode: Whether to use test mode (watermarked).
        enable_captions: Whether to generate captions.
    """

    audio_url: str = Field(..., description="URL of audio file")
    avatar_id: str = Field(..., description="HeyGen avatar ID")
    avatar_style: str = Field(default="normal", description="Avatar style")
    title: Optional[str] = Field(default=None, description="Video title")
    dimension: VideoDimension = Field(
        default_factory=VideoDimension, description="Video dimensions"
    )
    test_mode: bool = Field(default=False, description="Use test mode (watermarked)")
    enable_captions: bool = Field(default=True, description="Generate captions")

    def to_heygen_payload(self) -> dict:
        """
        Convert to HeyGen API v2 payload format.

        Returns:
            Dictionary formatted for HeyGen API v2.
        """
        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": self.avatar_id,
                        "avatar_style": self.avatar_style,
                    },
                    "voice": {
                        "type": "audio",
                        "audio_url": self.audio_url,
                    },
                }
            ],
            "test": self.test_mode,
            "caption": self.enable_captions,
            "dimension": {
                "width": self.dimension.width,
                "height": self.dimension.height,
            },
        }

        if self.title:
            payload["title"] = self.title

        return payload


class VideoGenerationResponse(BaseModel):
    """
    Model for video generation response/status.

    Attributes:
        video_id: Unique video ID from HeyGen.
        status: Current generation status.
        video_url: URL of completed video (when status is COMPLETED).
        error_message: Error message (when status is FAILED).
        created_at: When generation was started.
        completed_at: When generation completed.
        duration_seconds: Video duration in seconds.
    """

    video_id: str = Field(..., description="HeyGen video ID")
    status: VideoStatus = Field(default=VideoStatus.PENDING, description="Generation status")
    video_url: Optional[str] = Field(default=None, description="Completed video URL")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.now, description="Start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")
    duration_seconds: Optional[float] = Field(default=None, description="Video duration")

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Check if video generation is complete."""
        return self.status == VideoStatus.COMPLETED

    @computed_field
    @property
    def is_failed(self) -> bool:
        """Check if video generation failed."""
        return self.status == VideoStatus.FAILED

    @computed_field
    @property
    def is_pending(self) -> bool:
        """Check if video is still being generated."""
        return self.status in (VideoStatus.PENDING, VideoStatus.PROCESSING)


class YouTubeUploadRequest(BaseModel):
    """
    Model for YouTube video upload request.

    Attributes:
        file_path: Local path to the video file.
        title: Video title (max 100 chars).
        description: Video description (max 5000 chars).
        category_id: YouTube category ID.
        privacy_status: Video privacy setting.
        made_for_kids: Whether video is made for kids.
        tags: Optional list of tags.
    """

    file_path: str = Field(..., description="Path to video file")
    title: str = Field(..., max_length=100, description="Video title")
    description: str = Field(default="", max_length=5000, description="Video description")
    category_id: str = Field(default="22", description="YouTube category ID")
    privacy_status: str = Field(default="public", description="Privacy setting")
    made_for_kids: bool = Field(default=False, description="Made for kids flag")
    tags: list[str] = Field(default_factory=list, description="Video tags")

    @field_validator("privacy_status")
    @classmethod
    def validate_privacy(cls, v: str) -> str:
        """Validate privacy status."""
        valid = {"public", "private", "unlisted"}
        if v.lower() not in valid:
            raise ValueError(f"Privacy must be one of: {valid}")
        return v.lower()

    @field_validator("title", mode="before")
    @classmethod
    def truncate_title(cls, v: str) -> str:
        """Truncate title to YouTube's 100 char limit."""
        if len(v) > 100:
            return v[:97] + "..."
        return v

    def to_youtube_body(self) -> dict:
        """
        Convert to YouTube API body format.

        Returns:
            Dictionary formatted for YouTube Data API v3.
        """
        body = {
            "snippet": {
                "title": self.title,
                "description": self.description,
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": self.privacy_status,
                "selfDeclaredMadeForKids": self.made_for_kids,
            },
        }

        if self.tags:
            body["snippet"]["tags"] = self.tags

        return body


class YouTubeUploadResponse(BaseModel):
    """
    Model for YouTube upload response.

    Attributes:
        video_id: YouTube video ID.
        title: Uploaded video title.
        url: Full YouTube watch URL.
        upload_status: Upload status from YouTube.
        uploaded_at: Timestamp of successful upload.
    """

    video_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title")
    url: Optional[str] = Field(default=None, description="YouTube watch URL")
    upload_status: str = Field(default="uploaded", description="Upload status")
    uploaded_at: datetime = Field(default_factory=datetime.now, description="Upload timestamp")

    @computed_field
    @property
    def watch_url(self) -> str:
        """Generate YouTube watch URL."""
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @computed_field
    @property
    def studio_url(self) -> str:
        """Generate YouTube Studio edit URL."""
        return f"https://studio.youtube.com/video/{self.video_id}/edit"
