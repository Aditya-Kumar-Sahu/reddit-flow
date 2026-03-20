"""
Data models for Reddit-Flow.

This module provides Pydantic models for validating and serializing
data throughout the application.

Models:
    Reddit: RedditComment, RedditPost, LinkInfo
    Pipeline: ContentItem, ContentCandidate, DestinationSpec, ChannelSpec,
              ProviderSelection, PublishRequest, PublishResult,
              PipelineEvent, PipelineRequest, PipelineResult
    Script: VideoScript, ScriptGenerationRequest
    Video: VideoGenerationRequest, VideoGenerationResponse,
           YouTubeUploadRequest, YouTubeUploadResponse
"""

from reddit_flow.models.pipeline import (
    ChannelSpec,
    ContentCandidate,
    ContentItem,
    DestinationSpec,
    PipelineEvent,
    PipelineRequest,
    PipelineResult,
    ProviderSelection,
    PublishRequest,
    PublishResult,
    RenderProfile,
    ScriptBrief,
)
from reddit_flow.models.reddit import LinkInfo, RedditComment, RedditPost
from reddit_flow.models.script import ScriptGenerationRequest, VideoScript
from reddit_flow.models.video import (
    AudioAsset,
    VideoDimension,
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStatus,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
)

__all__ = [
    # Reddit models
    "RedditComment",
    "RedditPost",
    "LinkInfo",
    # Pipeline models
    "ContentItem",
    "ContentCandidate",
    "DestinationSpec",
    "ChannelSpec",
    "ProviderSelection",
    "ScriptBrief",
    "RenderProfile",
    "PublishRequest",
    "PublishResult",
    "PipelineEvent",
    "PipelineRequest",
    "PipelineResult",
    # Script models
    "VideoScript",
    "ScriptGenerationRequest",
    # Video models
    "VideoStatus",
    "VideoDimension",
    "AudioAsset",
    "VideoGenerationRequest",
    "VideoGenerationResponse",
    "YouTubeUploadRequest",
    "YouTubeUploadResponse",
]
