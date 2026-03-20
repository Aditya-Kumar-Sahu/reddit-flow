"""
Canonical pipeline models for multi-platform content workflows.

These models generalize the existing Reddit-specific workflow so new sources,
destinations, and messaging channels can share a common request/result shape.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from reddit_flow.models.script import VideoScript


class ContentItem(BaseModel):
    """Canonical content representation independent of the source platform."""

    source_type: str = Field(
        ..., description="Platform or source type, e.g. reddit, medium_article"
    )
    source_id: str = Field(..., description="External identifier from the source platform")
    source_url: str = Field(..., description="Canonical source URL")
    title: str = Field(..., description="Primary title or headline")
    body: str = Field(default="", description="Primary body text")
    summary: Optional[str] = Field(default=None, description="Optional short summary")
    author: Optional[str] = Field(default=None, description="Primary author")
    partial: bool = Field(default=False, description="Whether the item only has partial content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific metadata")
    comments: List[Dict[str, Any]] = Field(
        default_factory=list, description="Canonical comments/replies"
    )

    @field_validator("source_type", mode="before")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        """Normalize source type names for registry compatibility."""
        return str(value).strip().lower()

    @property
    def text_content(self) -> str:
        """Return a script-friendly text block from title and body."""
        parts = [part.strip() for part in (self.title, self.body) if part and part.strip()]
        return "\n\n".join(parts)


class ContentCandidate(BaseModel):
    """A lightweight candidate discovered from a feed or source listing."""

    source_type: str = Field(..., description="Platform or source type")
    candidate_id: str = Field(..., description="Candidate identifier")
    url: str = Field(..., description="Candidate URL")
    title: str = Field(..., description="Candidate title")
    summary: str = Field(default="", description="Candidate summary text")
    author: Optional[str] = Field(default=None, description="Candidate author")
    published_at: Optional[datetime] = Field(default=None, description="Publish timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional source metadata")

    @field_validator("source_type", mode="before")
    @classmethod
    def normalize_candidate_source_type(cls, value: str) -> str:
        """Normalize source type names."""
        return str(value).strip().lower()


class DestinationSpec(BaseModel):
    """Target publish destination configuration."""

    name: str = Field(..., description="Destination name, e.g. youtube or instagram")
    export_only: bool = Field(
        default=False, description="Generate publishable assets without direct publish"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Destination-specific options"
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalize destination names."""
        return str(value).strip().lower()


class ChannelSpec(BaseModel):
    """Messaging channel context for inbound/outbound interactions."""

    name: str = Field(..., description="Channel name, e.g. telegram or whatsapp")
    conversation_id: Optional[str] = Field(
        default=None, description="Conversation or chat identifier"
    )
    user_id: Optional[str] = Field(default=None, description="User identifier within the channel")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Channel-specific context")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_channel_name(cls, value: str) -> str:
        """Normalize channel names."""
        return str(value).strip().lower()


class ProviderSelection(BaseModel):
    """Preferred provider choices for the pipeline."""

    script_provider: str = Field(
        default="gemini", description="Preferred script-generation provider"
    )
    voice_provider: str = Field(
        default="elevenlabs", description="Preferred text-to-speech provider"
    )
    video_provider: str = Field(default="heygen", description="Preferred video-generation provider")
    script_fallbacks: List[str] = Field(
        default_factory=list, description="Fallback script providers"
    )
    voice_fallbacks: List[str] = Field(default_factory=list, description="Fallback voice providers")
    video_fallbacks: List[str] = Field(default_factory=list, description="Fallback video providers")

    @field_validator(
        "script_provider",
        "voice_provider",
        "video_provider",
        mode="before",
    )
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        """Normalize provider names."""
        return str(value).strip().lower()

    @field_validator(
        "script_fallbacks",
        "voice_fallbacks",
        "video_fallbacks",
        mode="before",
    )
    @classmethod
    def normalize_provider_lists(cls, value: Any) -> List[str]:
        """Allow provider fallback lists to be passed as CSV strings."""
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return [str(item).strip().lower() for item in value if str(item).strip()]


class ScriptBrief(BaseModel):
    """Target-specific script instructions used by the AI providers."""

    target: str = Field(..., description="Script target, e.g. youtube_video")
    tone: str = Field(default="conversational", description="Preferred narrative tone")
    max_words: int = Field(default=250, ge=20, le=2000, description="Maximum script length")
    hook_required: bool = Field(default=True, description="Whether the script needs a hook")
    cta_required: bool = Field(default=True, description="Whether the script needs a CTA")
    aspect_ratio: Optional[str] = Field(default=None, description="Preferred render aspect ratio")
    caption_style: str = Field(
        default="standard", description="Caption/style hint for the provider"
    )
    audience_notes: str = Field(default="", description="Target audience or delivery notes")

    @field_validator("target", mode="before")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        """Normalize script target names."""
        return str(value).strip().lower()


class RenderProfile(BaseModel):
    """Normalized render settings shared by video providers."""

    name: str = Field(..., description="Render profile name")
    width: int = Field(default=1080, ge=100, le=4096, description="Video width in pixels")
    height: int = Field(default=1920, ge=100, le=4096, description="Video height in pixels")
    enable_captions: bool = Field(default=True, description="Whether captions should be enabled")
    caption_style: str = Field(default="standard", description="Caption rendering style")
    background_format: str = Field(default="portrait", description="Portrait, landscape, or square")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalize render profile names."""
        return str(value).strip().lower()

    @property
    def aspect_ratio(self) -> str:
        """Calculate the aspect ratio in simplest form, e.g. 9:16 for 1080x1920."""
        from math import gcd

        divisor = gcd(self.width, self.height)
        return f"{self.width // divisor}:{self.height // divisor}"


class PublishRequest(BaseModel):
    """Canonical request to publish a rendered asset to a destination."""

    destination: str = Field(..., description="Destination identifier")
    media_url: Optional[str] = Field(default=None, description="URL of generated media to publish")
    script: VideoScript = Field(..., description="Script metadata to use for publish metadata")
    content_item: ContentItem = Field(..., description="Canonical source content")
    additional_description: str = Field(
        default="", description="Extra destination-specific description"
    )
    keep_local_file: bool = Field(
        default=False, description="Whether to keep downloaded assets locally"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Destination-specific options"
    )

    @field_validator("destination", mode="before")
    @classmethod
    def normalize_destination(cls, value: str) -> str:
        """Normalize destination identifiers."""
        return str(value).strip().lower()


class PublishResult(BaseModel):
    """Canonical publish result for a single destination."""

    destination: str = Field(..., description="Destination name")
    external_id: Optional[str] = Field(default=None, description="External publish identifier")
    title: Optional[str] = Field(default=None, description="Published title")
    url: Optional[str] = Field(default=None, description="Public destination URL")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Destination-specific metadata"
    )

    @field_validator("destination", mode="before")
    @classmethod
    def normalize_publish_destination(cls, value: str) -> str:
        """Normalize destination identifiers."""
        return str(value).strip().lower()


class PipelineEvent(BaseModel):
    """Channel-neutral event emitted during pipeline execution."""

    event_type: str = Field(..., description="Event type, e.g. status, error, completed")
    step: str = Field(..., description="Pipeline step")
    message: str = Field(..., description="Human-readable event message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured event metadata")
    created_at: datetime = Field(default_factory=datetime.now, description="Event timestamp")


class PipelineRequest(BaseModel):
    """Canonical request for source-agnostic pipeline execution."""

    source_url: str = Field(..., description="Source URL to process")
    source_type: Optional[str] = Field(default=None, description="Optional source type override")
    user_input: Optional[str] = Field(
        default=None, description="Optional user instructions or context"
    )
    destinations: List[DestinationSpec] = Field(
        default_factory=lambda: [DestinationSpec(name="youtube")],
        description="Publish destinations",
    )
    channel: Optional[ChannelSpec] = Field(default=None, description="Inbound messaging context")
    provider_selection: ProviderSelection = Field(
        default_factory=ProviderSelection,
        description="Preferred provider selection",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional pipeline options"
    )

    @field_validator("source_type", mode="before")
    @classmethod
    def normalize_optional_source_type(cls, value: Optional[str]) -> Optional[str]:
        """Normalize source type if provided."""
        if value is None:
            return None
        return str(value).strip().lower()

    @model_validator(mode="after")
    def validate_destinations(self) -> "PipelineRequest":
        """Ensure at least one publish destination exists."""
        if not self.destinations:
            raise ValueError("destinations must contain at least one destination")
        return self

    @property
    def primary_destination(self) -> str:
        """Expose the first destination for convenience."""
        return self.destinations[0].name


class PipelineResult(BaseModel):
    """Canonical result returned by the generic pipeline entry point."""

    workflow_id: str = Field(..., description="Pipeline workflow identifier")
    status: str = Field(default="pending", description="Overall pipeline status")
    started_at: datetime = Field(default_factory=datetime.now, description="Start timestamp")
    content_item: Optional[ContentItem] = Field(
        default=None, description="Resolved canonical content"
    )
    script: Optional[VideoScript] = Field(default=None, description="Generated script")
    media_result: Optional[Any] = Field(default=None, description="Generated media result")
    publish_results: List[PublishResult] = Field(
        default_factory=list, description="Publish results"
    )
    events: List[PipelineEvent] = Field(default_factory=list, description="Pipeline event stream")
    error: Optional[str] = Field(default=None, description="Error message when failed")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")

    @property
    def primary_publish_url(self) -> Optional[str]:
        """Return the first publish URL when available."""
        if not self.publish_results:
            return None
        return self.publish_results[0].url

    @property
    def duration_seconds(self) -> Optional[float]:
        """Return total pipeline duration in seconds when completed."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()
