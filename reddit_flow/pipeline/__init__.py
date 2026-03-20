"""
Pipeline contracts, registries, and provider adapters.

Source and publisher adapters are available from their dedicated modules to keep
package imports lightweight and avoid circular dependencies with services.
"""

from reddit_flow.pipeline.contracts import (
    MessageChannel,
    Publisher,
    ScriptProvider,
    SourceAdapter,
    VideoProvider,
    VoiceProvider,
)
from reddit_flow.pipeline.providers import (
    AnthropicScriptProvider,
    ElevenLabsVoiceProvider,
    GeminiScriptProvider,
    GoogleCloudTTSProvider,
    HeyGenVideoProvider,
    OpenAIScriptProvider,
    OpenAITTSProvider,
    TavusVideoProvider,
)
from reddit_flow.pipeline.registry import ProviderRegistry, SourceAdapterRegistry

__all__ = [
    "SourceAdapter",
    "ScriptProvider",
    "VoiceProvider",
    "VideoProvider",
    "Publisher",
    "MessageChannel",
    "ProviderRegistry",
    "SourceAdapterRegistry",
    "GeminiScriptProvider",
    "OpenAIScriptProvider",
    "AnthropicScriptProvider",
    "ElevenLabsVoiceProvider",
    "OpenAITTSProvider",
    "GoogleCloudTTSProvider",
    "HeyGenVideoProvider",
    "TavusVideoProvider",
]
