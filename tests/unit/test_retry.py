"""
Unit tests for retry utilities module.

Tests cover:
- RetryConfig validation and defaults
- with_retry decorator behavior
- CircuitBreaker state transitions
- Timeout handling
"""

import asyncio
import time

import pytest

from reddit_flow.exceptions import RetryableError
from reddit_flow.utils.retry import (
    AGGRESSIVE_RETRY_CONFIG,
    API_RETRY_CONFIG,
    CONSERVATIVE_RETRY_CONFIG,
    DEFAULT_RETRY_CONFIG,
    DEFAULT_TIMEOUT_CONFIG,
    FAST_TIMEOUT_CONFIG,
    VIDEO_TIMEOUT_CONFIG,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    RetryConfig,
    TimeoutConfig,
    TimeoutError,
    timeout_decorator,
    with_retry,
    with_retry_sync,
    with_timeout,
    with_timeout_async,
)

# =============================================================================
# RetryConfig Tests
# =============================================================================


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=0.5,
            max_delay=30.0,
        )
        assert config.max_attempts == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0

    def test_invalid_max_attempts(self):
        """Test validation of max_attempts."""
        with pytest.raises(ValueError, match="max_attempts must be at least 1"):
            RetryConfig(max_attempts=0)

    def test_invalid_base_delay(self):
        """Test validation of base_delay."""
        with pytest.raises(ValueError, match="base_delay cannot be negative"):
            RetryConfig(base_delay=-1)

    def test_invalid_max_delay(self):
        """Test validation of max_delay < base_delay."""
        with pytest.raises(ValueError, match="max_delay must be >= base_delay"):
            RetryConfig(base_delay=10, max_delay=5)

    def test_preset_configs_exist(self):
        """Test that preset configurations are valid."""
        assert DEFAULT_RETRY_CONFIG.max_attempts == 3
        assert AGGRESSIVE_RETRY_CONFIG.max_attempts == 5
        assert CONSERVATIVE_RETRY_CONFIG.max_attempts == 2
        assert API_RETRY_CONFIG.max_attempts == 3


# =============================================================================
# with_retry Decorator Tests
# =============================================================================


class TestWithRetry:
    """Tests for with_retry decorator."""

    def test_success_no_retry(self):
        """Test successful call doesn't retry."""
        call_count = 0

        @with_retry()
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_retries_on_retryable_error(self):
        """Test retries on RetryableError."""
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01))
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Temporary failure")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_retries_on_connection_error(self):
        """Test retries on ConnectionError."""
        call_count = 0

        @with_retry(RetryConfig(max_attempts=2, base_delay=0.01))
        def network_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network failure")
            return "connected"

        result = network_func()
        assert result == "connected"
        assert call_count == 2

    def test_raises_after_max_retries(self):
        """Test raises exception after max retries exhausted."""
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01))
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise RetryableError("Always fails")

        with pytest.raises(RetryableError, match="Always fails"):
            always_fails()

        assert call_count == 3

    def test_no_retry_on_non_retryable_error(self):
        """Test doesn't retry on non-retryable errors."""
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01))
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError, match="Not retryable"):
            raises_value_error()

        assert call_count == 1


class TestWithRetrySync:
    """Tests for with_retry_sync function."""

    def test_executes_function(self):
        """Test basic function execution."""

        def simple_func(x, y):
            return x + y

        result = with_retry_sync(simple_func, None, 1, 2)
        assert result == 3

    def test_retries_with_config(self):
        """Test retries with custom config."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RetryableError("Fail")
            return "ok"

        config = RetryConfig(max_attempts=3, base_delay=0.01)
        result = with_retry_sync(flaky_func, config)
        assert result == "ok"
        assert call_count == 2


# =============================================================================
# CircuitBreaker Tests
# =============================================================================


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_values(self):
        """Test default configuration."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout_seconds == 60.0


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_closed(self):
        """Test circuit starts in closed state."""
        breaker = CircuitBreaker("test_initial")
        assert breaker.state == CircuitState.CLOSED

    def test_opens_after_failures(self):
        """Test circuit opens after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test_opens", config)

        # Record failures
        for _ in range(3):
            breaker.record_failure(Exception("failure"))

        assert breaker.state == CircuitState.OPEN

    def test_blocks_when_open(self):
        """Test circuit blocks requests when open."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test_blocks", config)

        breaker.record_failure(Exception("failure"))

        assert not breaker.is_available()
        with pytest.raises(CircuitOpenError):
            breaker.call(lambda: "test")

    def test_transitions_to_half_open(self):
        """Test circuit transitions to half-open after timeout."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.01)
        breaker = CircuitBreaker("test_half_open", config)

        breaker.record_failure(Exception("failure"))
        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.02)

        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_after_successes(self):
        """Test circuit closes after success threshold in half-open."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.01,
        )
        breaker = CircuitBreaker("test_closes", config)

        # Open the circuit
        breaker.record_failure(Exception("failure"))
        time.sleep(0.02)  # Wait for half-open

        # Verify half-open state
        assert breaker.state == CircuitState.HALF_OPEN

        # Record successes
        breaker.record_success()
        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    def test_reopens_on_half_open_failure(self):
        """Test circuit reopens on failure in half-open state."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.01)
        breaker = CircuitBreaker("test_reopens", config)

        # Open then transition to half-open
        breaker.record_failure(Exception("failure"))
        time.sleep(0.02)
        assert breaker.state == CircuitState.HALF_OPEN

        # Fail again
        breaker.record_failure(Exception("failure"))
        assert breaker.state == CircuitState.OPEN

    def test_decorator_usage(self):
        """Test circuit breaker as decorator."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker("test_decorator", config)

        call_count = 0

        @breaker
        def maybe_fails(should_fail: bool):
            nonlocal call_count
            call_count += 1
            if should_fail:
                raise Exception("failure")
            return "success"

        # Successful calls
        assert maybe_fails(False) == "success"
        assert maybe_fails(False) == "success"
        assert breaker.state == CircuitState.CLOSED

        # Fail twice to open
        with pytest.raises(Exception):
            maybe_fails(True)
        with pytest.raises(Exception):
            maybe_fails(True)

        assert breaker.state == CircuitState.OPEN

    def test_context_manager_success(self):
        """Test circuit breaker as context manager with success."""
        breaker = CircuitBreaker("test_ctx_success")
        result = None
        with breaker:
            result = "success"

        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_context_manager_failure(self):
        """Test circuit breaker as context manager with failure."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test_ctx_failure", config)

        with pytest.raises(ValueError):
            with breaker:
                raise ValueError("error")

        assert breaker.state == CircuitState.OPEN

    def test_manual_reset(self):
        """Test manual circuit reset."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test_reset", config)

        breaker.record_failure(Exception("failure"))
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED

    def test_global_registry(self):
        """Test circuit breakers are registered globally."""
        breaker = CircuitBreaker("test_registry")

        found = CircuitBreaker.get("test_registry")
        assert found is breaker

    def test_get_all_states(self):
        """Test getting all circuit states."""
        CircuitBreaker("test_state_1")
        CircuitBreaker("test_state_2")

        states = CircuitBreaker.get_all_states()
        assert "test_state_1" in states
        assert "test_state_2" in states


# =============================================================================
# Timeout Tests
# =============================================================================


class TestTimeoutConfig:
    """Tests for TimeoutConfig."""

    def test_default_values(self):
        """Test default timeout values."""
        config = TimeoutConfig()
        assert config.default_timeout == 30.0
        assert config.connect_timeout == 10.0
        assert config.read_timeout == 60.0

    def test_as_tuple(self):
        """Test conversion to tuple."""
        config = TimeoutConfig(connect_timeout=5.0, read_timeout=30.0)
        assert config.as_tuple() == (5.0, 30.0)

    def test_preset_configs(self):
        """Test preset timeout configurations."""
        assert DEFAULT_TIMEOUT_CONFIG.default_timeout == 30.0
        assert VIDEO_TIMEOUT_CONFIG.default_timeout == 1800.0
        assert FAST_TIMEOUT_CONFIG.default_timeout == 10.0


class TestWithTimeout:
    """Tests for with_timeout function."""

    def test_completes_before_timeout(self):
        """Test function completes before timeout."""

        def quick_func():
            return "done"

        result = with_timeout(quick_func, timeout=1.0)
        assert result == "done"

    def test_raises_on_timeout(self):
        """Test raises TimeoutError when exceeded."""

        def slow_func():
            time.sleep(1.0)
            return "done"

        with pytest.raises(TimeoutError) as exc_info:
            with_timeout(slow_func, timeout=0.1)

        assert exc_info.value.timeout == 0.1

    def test_passes_arguments(self):
        """Test passes arguments to function."""

        def add(a, b):
            return a + b

        result = with_timeout(add, 1.0, 2, 3)
        assert result == 5

    def test_propagates_exception(self):
        """Test propagates function exceptions."""

        def raises():
            raise ValueError("error")

        with pytest.raises(ValueError, match="error"):
            with_timeout(raises, 1.0)


class TestWithTimeoutAsync:
    """Tests for with_timeout_async function."""

    @pytest.mark.asyncio
    async def test_completes_before_timeout(self):
        """Test async function completes before timeout."""

        async def quick_coro():
            return "done"

        result = await with_timeout_async(quick_coro(), timeout=1.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """Test raises TimeoutError when exceeded."""

        async def slow_coro():
            await asyncio.sleep(1.0)
            return "done"

        with pytest.raises(TimeoutError):
            await with_timeout_async(slow_coro(), timeout=0.1)


class TestTimeoutDecorator:
    """Tests for timeout_decorator."""

    def test_decorator_success(self):
        """Test decorator with successful completion."""

        @timeout_decorator(1.0)
        def quick_func():
            return "done"

        assert quick_func() == "done"

    def test_decorator_timeout(self):
        """Test decorator raises on timeout."""

        @timeout_decorator(0.1)
        def slow_func():
            time.sleep(1.0)
            return "done"

        with pytest.raises(TimeoutError):
            slow_func()

    def test_custom_message(self):
        """Test custom timeout message."""

        @timeout_decorator(0.1, message="Custom timeout message")
        def slow_func():
            time.sleep(1.0)

        with pytest.raises(TimeoutError, match="Custom timeout message"):
            slow_func()
