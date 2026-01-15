"""
Retry utilities and decorators.

This module provides configurable retry logic, circuit breaker pattern,
and timeout handling for resilient API operations.

Example usage:
    from reddit_flow.utils.retry import (
        RetryConfig,
        with_retry,
        CircuitBreaker,
        with_timeout,
    )

    # Simple retry with defaults
    @with_retry()
    def api_call():
        ...

    # Custom retry configuration
    config = RetryConfig(max_attempts=5, base_delay=2.0)
    @with_retry(config)
    def custom_api_call():
        ...

    # Circuit breaker for failing services
    breaker = CircuitBreaker("heygen_api", failure_threshold=5)
    with breaker:
        make_api_call()

    # Timeout wrapper
    result = with_timeout(api_call, timeout=30.0)
"""

import asyncio
import functools
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, Set, Type, TypeVar, Union

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from reddit_flow.exceptions import APIError, RedditFlowError, RetryableError, TransientAPIError

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Retry Configuration
# =============================================================================


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (including initial).
        base_delay: Base delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.
        exponential_base: Base for exponential backoff (default: 2).
        jitter: Whether to add random jitter to delays.
        retry_on: Exception types to retry on.
        stop_after_seconds: Optional total time limit for all retries.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: tuple = field(
        default_factory=lambda: (
            RetryableError,
            TransientAPIError,
            ConnectionError,
            TimeoutError,
        )
    )
    stop_after_seconds: Optional[float] = None

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay < 0:
            raise ValueError("base_delay cannot be negative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")


# Default configurations for different scenarios
DEFAULT_RETRY_CONFIG = RetryConfig()

AGGRESSIVE_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
)

CONSERVATIVE_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=2.0,
    max_delay=10.0,
)

API_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
    retry_on=(
        RetryableError,
        TransientAPIError,
        ConnectionError,
        TimeoutError,
        APIError,  # Retry all API errors
    ),
)


# =============================================================================
# Retry Decorator
# =============================================================================


def log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry attempt information."""
    if retry_state.attempt_number > 1:
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        logger.warning(
            "Retry attempt %d/%s for %s: %s",
            retry_state.attempt_number - 1,
            "?",  # Can't easily get max attempts here
            retry_state.fn.__name__ if retry_state.fn else "unknown",
            str(exception) if exception else "unknown error",
        )


def with_retry(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[RetryCallState], None]] = None,
) -> Callable[[F], F]:
    """
    Decorator that adds configurable retry logic to a function.

    Args:
        config: Retry configuration. Uses DEFAULT_RETRY_CONFIG if not provided.
        on_retry: Optional callback called on each retry attempt.

    Returns:
        Decorated function with retry logic.

    Example:
        @with_retry(RetryConfig(max_attempts=5))
        def flaky_api_call():
            ...
    """
    if config is None:
        config = DEFAULT_RETRY_CONFIG

    def decorator(func: F) -> F:
        """Apply retry logic to the decorated function."""
        # Build stop condition
        stop_conditions: list[Union[stop_after_attempt, stop_after_delay]] = [
            stop_after_attempt(config.max_attempts)
        ]
        if config.stop_after_seconds:
            stop_conditions.append(stop_after_delay(config.stop_after_seconds))

        # Build wait strategy
        wait_strategy = wait_exponential(
            multiplier=config.base_delay,
            max=config.max_delay,
            exp_base=config.exponential_base,
        )

        # Build retry condition
        retry_condition = retry_if_exception_type(config.retry_on)

        # Create the retry decorator
        retry_decorator = retry(
            stop=(
                stop_conditions[0]
                if len(stop_conditions) == 1
                else stop_conditions[0] | stop_conditions[1]
            ),
            wait=wait_strategy,
            retry=retry_condition,
            before_sleep=on_retry or log_retry_attempt,
            reraise=True,
        )

        return retry_decorator(func)

    return decorator


def with_retry_sync(
    func: Callable[..., T],
    config: Optional[RetryConfig] = None,
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Execute a function with retry logic (non-decorator version).

    Args:
        func: Function to execute.
        config: Retry configuration.
        *args: Positional arguments to pass to func.
        **kwargs: Keyword arguments to pass to func.

    Returns:
        Result of the function call.

    Example:
        result = with_retry_sync(api_call, config=AGGRESSIVE_RETRY_CONFIG, url="...")
    """
    decorated = with_retry(config)(func)
    return decorated(*args, **kwargs)


# =============================================================================
# Circuit Breaker Pattern
# =============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of failures before opening circuit.
        success_threshold: Successes needed in half-open to close.
        timeout_seconds: How long circuit stays open before half-open.
        excluded_exceptions: Exceptions that don't count as failures.
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    excluded_exceptions: Set[Type[Exception]] = field(default_factory=set)


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    When a service fails repeatedly, the circuit "opens" and immediately
    rejects requests for a timeout period. After the timeout, it enters
    "half-open" state and allows test requests through.

    Example:
        breaker = CircuitBreaker("heygen_api")

        @breaker
        def call_heygen():
            ...

        # Or as context manager
        with breaker:
            call_heygen()
    """

    # Class-level registry of all circuit breakers
    _breakers: dict[str, "CircuitBreaker"] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Unique identifier for this circuit.
            config: Circuit breaker configuration.
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state_lock = threading.Lock()

        # Register globally
        with CircuitBreaker._lock:
            CircuitBreaker._breakers[name] = self

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transitions."""
        with self._state_lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit '%s' entering half-open state", self.name)
            return self._state

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try resetting."""
        if self._last_failure_time is None:
            return True
        elapsed = datetime.now() - self._last_failure_time
        return elapsed >= timedelta(seconds=self.config.timeout_seconds)

    def record_success(self) -> None:
        """Record a successful operation."""
        with self._state_lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("Circuit '%s' closed after successful recovery", self.name)
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0

    def record_failure(self, exception: Exception) -> None:
        """Record a failed operation."""
        # Check if this exception type should be excluded
        if type(exception) in self.config.excluded_exceptions:
            return

        with self._state_lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning("Circuit '%s' reopened after failure in half-open state", self.name)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit '%s' opened after %d failures",
                        self.name,
                        self._failure_count,
                    )

    def is_available(self) -> bool:
        """Check if requests should be allowed through."""
        state = self.state  # This may trigger state transition
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        with self._state_lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info("Circuit '%s' manually reset", self.name)

    def __call__(self, func: F) -> F:
        """Use circuit breaker as a decorator."""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute function through circuit breaker."""
            return self.call(func, *args, **kwargs)

        return wrapper  # type: ignore

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Result of the function.

        Raises:
            CircuitOpenError: If circuit is open.
        """
        if not self.is_available():
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open",
                details={"circuit": self.name, "state": self._state.value},
            )

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise

    def __enter__(self) -> "CircuitBreaker":
        """Context manager entry."""
        if not self.is_available():
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open",
                details={"circuit": self.name, "state": self._state.value},
            )
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        if exc_val is None:
            self.record_success()
        elif isinstance(exc_val, Exception):
            self.record_failure(exc_val)
        # Don't suppress exceptions (implicitly returns None)

    @classmethod
    def get(cls, name: str) -> Optional["CircuitBreaker"]:
        """Get a circuit breaker by name."""
        return cls._breakers.get(name)

    @classmethod
    def get_all_states(cls) -> dict[str, CircuitState]:
        """Get states of all registered circuit breakers."""
        return {name: breaker.state for name, breaker in cls._breakers.items()}


class CircuitOpenError(RedditFlowError):
    """Raised when attempting to use an open circuit."""

    pass


# =============================================================================
# Timeout Handling
# =============================================================================


@dataclass
class TimeoutConfig:
    """
    Configuration for timeout behavior.

    Attributes:
        default_timeout: Default timeout in seconds.
        connect_timeout: Timeout for establishing connections.
        read_timeout: Timeout for reading responses.
    """

    default_timeout: float = 30.0
    connect_timeout: float = 10.0
    read_timeout: float = 60.0

    def as_tuple(self) -> tuple[float, float]:
        """Return (connect_timeout, read_timeout) tuple for requests library."""
        return (self.connect_timeout, self.read_timeout)


DEFAULT_TIMEOUT_CONFIG = TimeoutConfig()

# Longer timeouts for video generation
VIDEO_TIMEOUT_CONFIG = TimeoutConfig(
    default_timeout=1800.0,  # 30 minutes
    connect_timeout=30.0,
    read_timeout=1800.0,
)

# Short timeouts for quick API calls
FAST_TIMEOUT_CONFIG = TimeoutConfig(
    default_timeout=10.0,
    connect_timeout=5.0,
    read_timeout=10.0,
)


class TimeoutError(RedditFlowError):
    """Raised when an operation times out."""

    def __init__(
        self,
        message: str,
        timeout: float,
        details: Optional[dict[str, Any]] = None,
    ):
        """Initialize timeout error with duration info."""
        details = details or {}
        details["timeout_seconds"] = timeout
        super().__init__(message, details)
        self.timeout = timeout


def with_timeout(
    func: Callable[..., T],
    timeout: float,
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Execute a synchronous function with a timeout.

    Args:
        func: Function to execute.
        timeout: Timeout in seconds.
        *args: Positional arguments for func.
        **kwargs: Keyword arguments for func.

    Returns:
        Result of the function.

    Raises:
        TimeoutError: If execution exceeds timeout.

    Note:
        This uses threading and may not interrupt all blocking operations.
        For true cancellation, use async functions with asyncio.wait_for.
    """
    result: Any = None
    exception: Optional[Exception] = None
    completed = threading.Event()

    def target():
        """Execute function in thread and capture result."""
        nonlocal result, exception
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            exception = e
        finally:
            completed.set()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    if not completed.wait(timeout):
        raise TimeoutError(
            f"Operation timed out after {timeout} seconds",
            timeout=timeout,
            details={"function": func.__name__},
        )

    if exception:
        raise exception

    return result


async def with_timeout_async(
    coro: Any,
    timeout: float,
) -> Any:
    """
    Execute an async coroutine with a timeout.

    Args:
        coro: Coroutine to execute.
        timeout: Timeout in seconds.

    Returns:
        Result of the coroutine.

    Raises:
        TimeoutError: If execution exceeds timeout.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"Async operation timed out after {timeout} seconds",
            timeout=timeout,
        )


def timeout_decorator(
    timeout: float,
    message: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator that adds timeout to a function.

    Args:
        timeout: Timeout in seconds.
        message: Optional custom timeout message.

    Returns:
        Decorated function.

    Example:
        @timeout_decorator(30.0)
        def slow_operation():
            ...
    """

    def decorator(func: F) -> F:
        """Apply timeout to the decorated function."""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute function with timeout."""
            try:
                return with_timeout(func, timeout, *args, **kwargs)
            except TimeoutError as e:
                if message:
                    raise TimeoutError(message, timeout=timeout) from e
                raise

        return wrapper  # type: ignore

    return decorator
