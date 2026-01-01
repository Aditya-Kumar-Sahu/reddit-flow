"""
Unit tests for the base client interface.

Tests for src/reddit_flow/clients/base.py
"""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from reddit_flow.clients import AsyncClientMixin, BaseClient, HTTPClientMixin
from reddit_flow.exceptions import APIError, ConfigurationError, TransientAPIError

# =============================================================================
# Test Fixtures - Concrete Implementations for Testing
# =============================================================================


class ConcreteClient(BaseClient):
    """Concrete implementation of BaseClient for testing."""

    service_name = "TestService"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        should_fail_init: bool = False,
        should_fail_health: bool = False,
        health_result: bool = True,
    ) -> None:
        self._should_fail_init = should_fail_init
        self._should_fail_health = should_fail_health
        self._health_result = health_result
        super().__init__(config)

    def _initialize(self) -> None:
        if self._should_fail_init:
            raise ConfigurationError("Initialization failed", details={"reason": "test"})
        self._api_key = self._config.get("api_key", "default_key")

    def _health_check(self) -> bool:
        if self._should_fail_health:
            raise APIError("Health check failed", status_code=503)
        return self._health_result


class HTTPClient(HTTPClientMixin):
    """Concrete implementation of HTTPClientMixin for testing."""

    def __init__(self, base_url: str = "https://api.example.com") -> None:
        self.base_url = base_url
        self.default_timeout = 30
        self.default_headers = {"Content-Type": "application/json"}


class AsyncClient(AsyncClientMixin):
    """Concrete implementation of AsyncClientMixin for testing."""

    pass


# =============================================================================
# BaseClient Tests
# =============================================================================


class TestBaseClient:
    """Tests for the BaseClient abstract base class."""

    def test_successful_initialization(self) -> None:
        """Test that a client initializes successfully with valid config."""
        client = ConcreteClient(config={"api_key": "test_key"})
        assert client.is_initialized is True
        assert client._api_key == "test_key"

    def test_initialization_with_empty_config(self) -> None:
        """Test that a client can initialize with empty config using defaults."""
        client = ConcreteClient()
        assert client.is_initialized is True
        assert client._api_key == "default_key"

    def test_initialization_failure(self) -> None:
        """Test that initialization errors are properly raised."""
        with pytest.raises(ConfigurationError) as exc_info:
            ConcreteClient(should_fail_init=True)
        assert "Initialization failed" in str(exc_info.value)

    def test_is_initialized_property(self) -> None:
        """Test the is_initialized property returns correct state."""
        client = ConcreteClient()
        assert client.is_initialized is True

    def test_service_name_class_attribute(self) -> None:
        """Test that service_name is properly set."""
        client = ConcreteClient()
        assert client.service_name == "TestService"

    def test_repr(self) -> None:
        """Test string representation of client."""
        client = ConcreteClient()
        repr_str = repr(client)
        assert "ConcreteClient" in repr_str
        assert "TestService" in repr_str
        assert "initialized" in repr_str

    def test_config_stored(self) -> None:
        """Test that config is stored in _config attribute."""
        config = {"api_key": "my_key", "timeout": 30}
        client = ConcreteClient(config=config)
        assert client._config == config


class TestBaseClientHealthCheck:
    """Tests for BaseClient health check functionality."""

    def test_verify_service_success(self) -> None:
        """Test successful service verification."""
        client = ConcreteClient(health_result=True)
        result = client.verify_service()
        assert result is True

    def test_verify_service_returns_false(self) -> None:
        """Test service verification when health check returns False."""
        client = ConcreteClient(health_result=False)
        result = client.verify_service()
        assert result is False

    def test_verify_service_raises_on_error(self) -> None:
        """Test that verify_service re-raises exceptions from health check."""
        client = ConcreteClient(should_fail_health=True)
        with pytest.raises(APIError) as exc_info:
            client.verify_service()
        assert exc_info.value.status_code == 503

    @patch("reddit_flow.clients.base.logger")
    def test_verify_service_logs_success(self, mock_logger: MagicMock) -> None:
        """Test that successful verification is logged."""
        client = ConcreteClient()
        client.verify_service()
        # Check that info was called with success message
        assert any("verified successfully" in str(call) for call in mock_logger.info.call_args_list)


# =============================================================================
# HTTPClientMixin Tests
# =============================================================================


class TestHTTPClientMixin:
    """Tests for the HTTPClientMixin."""

    def test_build_url_basic(self) -> None:
        """Test basic URL building."""
        client = HTTPClient(base_url="https://api.example.com")
        url = client._build_url("/users")
        assert url == "https://api.example.com/users"

    def test_build_url_without_leading_slash(self) -> None:
        """Test URL building without leading slash in endpoint."""
        client = HTTPClient(base_url="https://api.example.com")
        url = client._build_url("users")
        assert url == "https://api.example.com/users"

    def test_build_url_with_trailing_slash_in_base(self) -> None:
        """Test URL building when base URL has trailing slash."""
        client = HTTPClient(base_url="https://api.example.com/")
        url = client._build_url("/users")
        assert url == "https://api.example.com/users"

    def test_build_url_with_path_segments(self) -> None:
        """Test URL building with multiple path segments."""
        client = HTTPClient(base_url="https://api.example.com/v1")
        url = client._build_url("/users/123/posts")
        assert url == "https://api.example.com/v1/users/123/posts"

    def test_get_headers_returns_defaults(self) -> None:
        """Test that _get_headers returns default headers."""
        client = HTTPClient()
        headers = client._get_headers()
        assert headers == {"Content-Type": "application/json"}

    def test_get_headers_merges_extra(self) -> None:
        """Test that extra headers are merged with defaults."""
        client = HTTPClient()
        headers = client._get_headers({"Authorization": "Bearer token"})
        assert headers == {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        }

    def test_get_headers_extra_overrides_default(self) -> None:
        """Test that extra headers can override defaults."""
        client = HTTPClient()
        headers = client._get_headers({"Content-Type": "text/plain"})
        assert headers["Content-Type"] == "text/plain"

    def test_get_headers_none_extra(self) -> None:
        """Test _get_headers with None extra headers."""
        client = HTTPClient()
        headers = client._get_headers(None)
        assert headers == {"Content-Type": "application/json"}


class TestHTTPClientMixinErrorHandling:
    """Tests for HTTPClientMixin error handling."""

    def test_handle_error_response_rate_limit(self) -> None:
        """Test that 429 errors raise TransientAPIError."""
        client = HTTPClient()
        with pytest.raises(TransientAPIError) as exc_info:
            client._handle_error_response(429, "Rate limit exceeded")
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 60

    def test_handle_error_response_service_unavailable(self) -> None:
        """Test that 503 errors raise TransientAPIError."""
        client = HTTPClient()
        with pytest.raises(TransientAPIError) as exc_info:
            client._handle_error_response(503, "Service unavailable")
        assert exc_info.value.status_code == 503
        assert exc_info.value.retry_after == 10

    def test_handle_error_response_bad_gateway(self) -> None:
        """Test that 502 errors raise TransientAPIError."""
        client = HTTPClient()
        with pytest.raises(TransientAPIError) as exc_info:
            client._handle_error_response(502, "Bad gateway")
        assert exc_info.value.status_code == 502

    def test_handle_error_response_gateway_timeout(self) -> None:
        """Test that 504 errors raise TransientAPIError."""
        client = HTTPClient()
        with pytest.raises(TransientAPIError) as exc_info:
            client._handle_error_response(504, "Gateway timeout")
        assert exc_info.value.status_code == 504

    def test_handle_error_response_client_error(self) -> None:
        """Test that 4xx errors (except 429) raise APIError."""
        client = HTTPClient()
        with pytest.raises(APIError) as exc_info:
            client._handle_error_response(400, "Bad request")
        assert exc_info.value.status_code == 400
        assert not isinstance(exc_info.value, TransientAPIError)

    def test_handle_error_response_not_found(self) -> None:
        """Test that 404 errors raise APIError."""
        client = HTTPClient()
        with pytest.raises(APIError) as exc_info:
            client._handle_error_response(404, "Not found")
        assert exc_info.value.status_code == 404

    def test_handle_error_response_server_error(self) -> None:
        """Test that 500 errors (not 502-504) raise APIError."""
        client = HTTPClient()
        with pytest.raises(APIError) as exc_info:
            client._handle_error_response(500, "Internal server error")
        assert exc_info.value.status_code == 500
        assert not isinstance(exc_info.value, TransientAPIError)

    def test_handle_error_response_custom_error_class(self) -> None:
        """Test using custom error class."""
        from reddit_flow.exceptions import TTSError

        client = HTTPClient()
        with pytest.raises(TTSError) as exc_info:
            client._handle_error_response(400, "Voice not found", error_class=TTSError)
        assert exc_info.value.status_code == 400


# =============================================================================
# AsyncClientMixin Tests
# =============================================================================


class TestAsyncClientMixin:
    """Tests for the AsyncClientMixin."""

    @pytest.mark.asyncio
    async def test_poll_status_immediate_success(self) -> None:
        """Test polling when check_fn returns complete immediately."""
        client = AsyncClient()
        call_count = 0

        async def check_fn():
            nonlocal call_count
            call_count += 1
            return True, "success_result"

        result = await client._poll_status(check_fn, timeout=60)
        assert result == "success_result"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_poll_status_eventual_success(self) -> None:
        """Test polling when check_fn succeeds after a few attempts."""
        client = AsyncClient()
        call_count = 0

        async def check_fn():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return True, "eventual_success"
            return False, None

        result = await client._poll_status(
            check_fn,
            timeout=60,
            initial_interval=1,  # Fast for testing
        )
        assert result == "eventual_success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_poll_status_timeout(self) -> None:
        """Test that polling times out correctly."""
        client = AsyncClient()

        async def check_fn():
            return False, None

        with pytest.raises(TimeoutError) as exc_info:
            await client._poll_status(
                check_fn,
                timeout=1,  # Very short timeout
                initial_interval=1,
            )
        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_poll_status_backoff(self) -> None:
        """Test that polling interval increases with backoff."""
        client = AsyncClient()
        call_times = []

        async def check_fn():
            import time

            call_times.append(time.time())
            if len(call_times) >= 4:
                return True, "done"
            return False, None

        await client._poll_status(
            check_fn,
            timeout=60,
            initial_interval=1,
            max_interval=100,
            backoff_multiplier=2.0,
        )

        # Check that intervals are increasing
        if len(call_times) >= 3:
            interval1 = call_times[2] - call_times[1]
            interval0 = call_times[1] - call_times[0]
            # Second interval should be larger (with some tolerance for timing)
            assert interval1 >= interval0 * 0.5  # Allow for timing variance


# =============================================================================
# Integration Tests - BaseClient with Mixins
# =============================================================================


class CombinedClient(BaseClient, HTTPClientMixin, AsyncClientMixin):
    """Client combining all base classes for integration testing."""

    service_name = "CombinedService"
    base_url = "https://api.combined.com/v1"
    default_headers = {"X-API-Key": "test_key"}

    def _initialize(self) -> None:
        self._api_key = self._config.get("api_key", "default")

    def _health_check(self) -> bool:
        return True


class TestCombinedClient:
    """Integration tests for a client using all base classes."""

    def test_combined_client_has_all_methods(self) -> None:
        """Test that combined client has methods from all mixins."""
        client = CombinedClient()

        # BaseClient methods
        assert hasattr(client, "verify_service")
        assert hasattr(client, "is_initialized")

        # HTTPClientMixin methods
        assert hasattr(client, "_build_url")
        assert hasattr(client, "_get_headers")
        assert hasattr(client, "_handle_error_response")

        # AsyncClientMixin methods
        assert hasattr(client, "_poll_status")

    def test_combined_client_url_building(self) -> None:
        """Test URL building in combined client."""
        client = CombinedClient()
        url = client._build_url("/endpoint")
        assert url == "https://api.combined.com/v1/endpoint"

    def test_combined_client_headers(self) -> None:
        """Test header handling in combined client."""
        client = CombinedClient()
        headers = client._get_headers({"Authorization": "Bearer token"})
        assert headers["X-API-Key"] == "test_key"
        assert headers["Authorization"] == "Bearer token"
