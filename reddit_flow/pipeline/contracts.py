"""Abstract contracts for the source-agnostic pipeline layer."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from reddit_flow.models import AudioAsset, RenderProfile
from reddit_flow.models.pipeline import (
    ContentItem,
    PipelineEvent,
    PipelineRequest,
    PublishRequest,
    PublishResult,
)


class SourceAdapter(ABC):
    """Contract for fetching canonical content from a source platform."""

    source_name: str = "unknown"

    @abstractmethod
    def supports(self, request: PipelineRequest) -> bool:
        """Return whether this adapter can process the given request."""

    @abstractmethod
    def fetch_content(self, request: PipelineRequest) -> ContentItem:
        """Resolve and return canonical content for the request."""


class ScriptProvider(ABC):
    """Contract for script generation providers."""

    provider_name: str = "unknown"

    @abstractmethod
    async def generate_script(self, content: ContentItem, request: PipelineRequest) -> Any:
        """Generate a script for the provided content."""


class VoiceProvider(ABC):
    """Contract for text-to-speech providers."""

    provider_name: str = "unknown"

    @abstractmethod
    def generate_audio(self, text: str, request: PipelineRequest) -> bytes:
        """Generate audio bytes from text."""


class VideoProvider(ABC):
    """Contract for video generation providers."""

    provider_name: str = "unknown"

    @abstractmethod
    def start_video_generation(
        self,
        audio_asset: AudioAsset,
        title: Optional[str] = None,
        avatar_id: Optional[str] = None,
        test_mode: bool = False,
        render_profile: Optional[RenderProfile] = None,
    ) -> str:
        """Start video generation from uploaded audio."""

    @abstractmethod
    async def wait_for_video(
        self,
        video_id: str,
        update_callback: Optional[Any] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """Wait for video generation to complete."""


class Publisher(ABC):
    """Contract for publish destinations."""

    destination_name: str = "unknown"

    @abstractmethod
    def publish(self, request: PublishRequest) -> PublishResult:
        """Publish a rendered asset to a destination."""


class MessageChannel(ABC):
    """Contract for inbound/outbound messaging channels."""

    channel_name: str = "unknown"

    @abstractmethod
    async def send_event(self, event: PipelineEvent) -> Any:
        """Send a pipeline event to the channel."""
