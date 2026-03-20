"""Registries for source adapters and named pipeline providers."""

from collections.abc import Iterable, Sequence
from typing import Dict, Generic, List, Optional, TypeVar

from reddit_flow.models.pipeline import PipelineRequest
from reddit_flow.pipeline.contracts import SourceAdapter

T = TypeVar("T")


class ProviderRegistry(Generic[T]):
    """Simple named component registry with fallback resolution."""

    def __init__(self, provider_kind: str) -> None:
        self.provider_kind = provider_kind
        self._providers: Dict[str, T] = {}

    def register(self, name: str, provider: T) -> None:
        """Register a provider under a normalized name."""
        key = name.strip().lower()
        if key in self._providers:
            raise ValueError(f"{self.provider_kind} provider '{key}' is already registered")
        self._providers[key] = provider

    def get(self, name: str) -> T:
        """Get a provider by name."""
        key = name.strip().lower()
        if key not in self._providers:
            raise LookupError(f"Unknown {self.provider_kind} provider: {key}")
        return self._providers[key]

    def resolve(
        self,
        preferred: Optional[str] = None,
        fallbacks: Optional[Sequence[str]] = None,
    ) -> T:
        """Resolve a provider using preferred and fallback names."""
        candidates: List[str] = []
        if preferred:
            candidates.append(preferred)
        if fallbacks:
            candidates.extend(fallbacks)

        for candidate in candidates:
            key = candidate.strip().lower()
            if key in self._providers:
                return self._providers[key]

        if not candidates and len(self._providers) == 1:
            return next(iter(self._providers.values()))

        raise LookupError(
            f"No {self.provider_kind} provider available for preferred={preferred!r} "
            f"fallbacks={list(fallbacks or [])!r}"
        )

    def names(self) -> List[str]:
        """List registered provider names."""
        return list(self._providers.keys())


class SourceAdapterRegistry:
    """Registry that resolves the first source adapter supporting a request."""

    def __init__(self, adapters: Optional[Iterable[SourceAdapter]] = None) -> None:
        self._adapters: List[SourceAdapter] = []
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: SourceAdapter) -> None:
        """Register a source adapter."""
        if any(existing.source_name == adapter.source_name for existing in self._adapters):
            raise ValueError(f"Source adapter '{adapter.source_name}' is already registered")
        self._adapters.append(adapter)

    def resolve(self, request: PipelineRequest) -> SourceAdapter:
        """Resolve the first adapter that supports the request."""
        for adapter in self._adapters:
            if adapter.supports(request):
                return adapter
        raise LookupError(f"No source adapter found for request: {request.source_url}")

    def names(self) -> List[str]:
        """List registered source adapter names."""
        return [adapter.source_name for adapter in self._adapters]
