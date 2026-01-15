"""
Base client interface for Reddit-Flow API clients.

This module defines the abstract base class that all API clients must implement,
providing a consistent interface and common functionality across all external
service integrations.

Design Principles:
    - All clients share a common initialization pattern
    - Health checks are standardized across all services
    - Retry logic is configurable per-client
    - Logging is consistent and structured
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional, Type

from reddit_flow.config import get_logger
from reddit_flow.exceptions import APIError

logger = get_logger(__name__)


class BaseClient(ABC):
    """
    Abstract base class for all API clients.

    This class defines the interface that all API clients must implement,
    ensuring consistent behavior across Reddit, Gemini, ElevenLabs, HeyGen,
    and YouTube integrations.

    Subclasses must implement:
        - _initialize(): Set up client-specific resources
        - _health_check(): Verify service connectivity
        - service_name: Class attribute identifying the service

    Attributes:
        service_name: Human-readable name of the service (class attribute).
        is_initialized: Whether the client has been successfully initialized.
        _config: Optional configuration dictionary.

    Example:
        >>> class MyAPIClient(BaseClient):
        ...     service_name = "MyAPI"
        ...
        ...     def _initialize(self) -> None:
        ...         self._api = SomeAPI(self._config["api_key"])
        ...
        ...     def _health_check(self) -> bool:
        ...         return self._api.ping()
    """

    service_name: ClassVar[str] = "Unknown"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the base client.

        Args:
            config: Optional configuration dictionary. If not provided,
                    the client should fall back to environment variables.

        Raises:
            ConfigurationError: If required configuration is missing.
        """
        self._config = config or {}
        self._is_initialized = False
        self._initialize()
        self._is_initialized = True
        logger.info(f"{self.service_name} client initialized")

    @abstractmethod
    def _initialize(self) -> None:
        """
        Perform client-specific initialization.

        This method is called during __init__ and should set up any
        client-specific resources, connections, or state.

        Subclasses should:
            - Load configuration (from self._config or environment)
            - Initialize API clients or connections
            - Validate that required credentials are present

        Raises:
            ConfigurationError: If required configuration is missing.
            APIError: If initialization fails due to API issues.
        """
        pass

    @abstractmethod
    def _health_check(self) -> bool:
        """
        Verify service connectivity and availability.

        This method should perform a lightweight check to verify that
        the service is reachable and the credentials are valid.

        Returns:
            True if the service is healthy and accessible.

        Raises:
            APIError: If the health check fails with an error.
        """
        pass

    @property
    def is_initialized(self) -> bool:
        """Return whether the client has been successfully initialized."""
        return self._is_initialized

    def verify_service(self) -> bool:
        """
        Verify that the service is accessible and credentials are valid.

        This is a public wrapper around _health_check that adds logging
        and standardized error handling.

        Returns:
            True if the service is healthy.

        Raises:
            APIError: If verification fails.
        """
        try:
            logger.debug(f"Verifying {self.service_name} service...")
            result = self._health_check()
            if result:
                logger.info(f"{self.service_name} service verified successfully")
            else:
                logger.warning(f"{self.service_name} service check returned False")
            return result
        except Exception as e:
            logger.error(f"{self.service_name} service verification failed: {e}")
            raise

    def __repr__(self) -> str:
        """Return string representation of the client."""
        status = "initialized" if self._is_initialized else "not initialized"
        return f"<{self.__class__.__name__}({self.service_name}, {status})>"


class HTTPClientMixin:
    """
    Mixin providing common HTTP client functionality.

    This mixin provides shared utilities for clients that interact with
    REST APIs over HTTP, including header management, timeout handling,
    and response parsing.

    Attributes:
        base_url: Base URL for API requests.
        default_timeout: Default request timeout in seconds.
        default_headers: Headers included in all requests.
    """

    base_url: str = ""
    default_timeout: int = 60
    default_headers: Dict[str, str] = {}

    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from base URL and endpoint.

        Args:
            endpoint: API endpoint path (with or without leading slash).

        Returns:
            Full URL string.

        Example:
            >>> client.base_url = "https://api.example.com/v1"
            >>> client._build_url("/users")
            'https://api.example.com/v1/users'
        """
        endpoint = endpoint.lstrip("/")
        base = self.base_url.rstrip("/")
        return f"{base}/{endpoint}"

    def _get_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Merge default headers with extra headers.

        Args:
            extra_headers: Additional headers to include in the request.

        Returns:
            Combined headers dictionary.
        """
        headers = self.default_headers.copy()
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _handle_error_response(
        self,
        status_code: int,
        response_body: str,
        error_class: Type[APIError] = APIError,
    ) -> None:
        """
        Handle HTTP error responses with appropriate exceptions.

        Args:
            status_code: HTTP status code.
            response_body: Response body text.
            error_class: Exception class to raise (defaults to APIError).

        Raises:
            APIError: Always raises with appropriate details.
        """
        from reddit_flow.exceptions import TransientAPIError

        # Determine if this is a retryable error
        if status_code in (429, 502, 503, 504):
            raise TransientAPIError(
                f"Service temporarily unavailable (HTTP {status_code})",
                status_code=status_code,
                response_body=response_body,
                retry_after=60 if status_code == 429 else 10,
            )

        raise error_class(
            f"Request failed with status {status_code}",
            status_code=status_code,
            response_body=response_body,
        )


class AsyncClientMixin:
    """
    Mixin providing async operation support.

    This mixin provides utilities for clients that need to perform
    asynchronous operations, such as polling for video generation
    status or handling long-running tasks.
    """

    async def _poll_status(
        self,
        check_fn: Any,
        timeout: int = 1800,
        initial_interval: int = 10,
        max_interval: int = 60,
        backoff_multiplier: float = 1.5,
    ) -> Any:
        """
        Poll for status with exponential backoff.

        Args:
            check_fn: Async function that returns (is_complete, result).
            timeout: Maximum time to wait in seconds.
            initial_interval: Initial polling interval in seconds.
            max_interval: Maximum polling interval in seconds.
            backoff_multiplier: Multiplier for exponential backoff.

        Returns:
            Result from check_fn when complete.

        Raises:
            TimeoutError: If timeout is exceeded.
            APIError: If status check fails.
        """
        import asyncio
        import time

        start_time = time.time()
        interval: float = initial_interval

        while time.time() - start_time < timeout:
            is_complete, result = await check_fn()
            if is_complete:
                return result

            await asyncio.sleep(interval)
            interval = min(interval * backoff_multiplier, max_interval)

        raise TimeoutError(f"Operation timed out after {timeout} seconds")
