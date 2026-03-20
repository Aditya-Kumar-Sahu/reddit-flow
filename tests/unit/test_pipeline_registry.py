"""Unit tests for pipeline registries and contracts."""

from typing import Any

import pytest

from reddit_flow.models import ContentItem, PipelineRequest
from reddit_flow.pipeline.contracts import SourceAdapter
from reddit_flow.pipeline.registry import ProviderRegistry, SourceAdapterRegistry


class DummySourceAdapter(SourceAdapter):
    """Minimal source adapter used for registry tests."""

    source_name = "dummy"

    def supports(self, request: PipelineRequest) -> bool:
        return "example.com" in request.source_url

    def fetch_content(self, request: PipelineRequest) -> ContentItem:
        return ContentItem(
            source_type="dummy",
            source_id="dummy-1",
            source_url=request.source_url,
            title="Dummy content",
            body="Dummy body",
        )


class TestSourceAdapterRegistry:
    """Tests for selecting source adapters."""

    def test_resolve_returns_first_supported_adapter(self):
        """The registry should locate a matching adapter for a request."""
        registry = SourceAdapterRegistry()
        adapter = DummySourceAdapter()
        registry.register(adapter)

        resolved = registry.resolve(PipelineRequest(source_url="https://example.com/story"))

        assert resolved is adapter

    def test_resolve_raises_for_unknown_request(self):
        """Requests with no supported source should fail clearly."""
        registry = SourceAdapterRegistry()
        registry.register(DummySourceAdapter())

        with pytest.raises(LookupError, match="No source adapter"):
            registry.resolve(PipelineRequest(source_url="https://unsupported.test/story"))


class TestProviderRegistry:
    """Tests for provider selection with fallbacks."""

    def test_resolve_returns_preferred_provider(self):
        """A preferred provider should win when registered."""
        registry = ProviderRegistry[Any](provider_kind="script")
        gemini = object()
        registry.register("gemini", gemini)

        assert registry.resolve(preferred="gemini") is gemini

    def test_resolve_uses_fallback_order(self):
        """Fallbacks should be tried in order when the preferred provider is missing."""
        registry = ProviderRegistry[Any](provider_kind="script")
        openai = object()
        gemini = object()
        registry.register("openai", openai)
        registry.register("gemini", gemini)

        resolved = registry.resolve(preferred="anthropic", fallbacks=["openai", "gemini"])

        assert resolved is openai
