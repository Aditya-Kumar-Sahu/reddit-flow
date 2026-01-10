# Exception Handling Guide

This document describes the error handling strategy in reddit-flow.

## Exception Hierarchy

All custom exceptions inherit from `RedditFlowError`:

```
RedditFlowError (base)
│
├── Configuration Errors
│   └── ConfigurationError      # Missing API keys, invalid config
│
├── Input Validation Errors
│   ├── ValidationError         # Generic validation failure
│   └── InvalidURLError         # Malformed Reddit URL
│
├── Content Processing Errors
│   └── ContentError            # Failed to process content
│
├── API Errors (all inherit from APIError)
│   ├── APIError                # Base for all API failures
│   │   ├── RedditAPIError      # Reddit PRAW failures
│   │   ├── AIGenerationError   # Gemini AI errors
│   │   ├── TTSError            # ElevenLabs failures
│   │   ├── VideoGenerationError# HeyGen failures
│   │   └── YouTubeUploadError  # YouTube API failures
│   │
│   ├── RetryableError          # Errors that should trigger retry
│   │   └── TransientAPIError   # Temporary API issues
│   │
│   └── QuotaExceededError      # API rate limits
│
└── Media Errors
    └── MediaGenerationError    # Audio/video creation failed
```

## Exception Classes

### Base Exception

```python
class RedditFlowError(Exception):
    """Base exception for all reddit-flow errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
```

### Configuration Errors

```python
class ConfigurationError(RedditFlowError):
    """Raised when configuration is missing or invalid."""
    pass

# Example usage:
if not settings.gemini_api_key:
    raise ConfigurationError(
        "Missing Gemini API key",
        details={"setting": "GOOGLE_API_KEY"}
    )
```

### API Errors

```python
class APIError(RedditFlowError):
    """Base class for API-related errors."""

    def __init__(self, message: str, status_code: int | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.status_code = status_code

class RedditAPIError(APIError):
    """Reddit API specific errors."""
    pass

class AIGenerationError(APIError):
    """Gemini AI generation failures."""
    pass

class TTSError(APIError):
    """ElevenLabs text-to-speech errors."""
    pass

class VideoGenerationError(APIError):
    """HeyGen video generation errors."""
    pass

class YouTubeUploadError(APIError):
    """YouTube upload failures."""
    pass
```

### Retryable Errors

```python
class RetryableError(APIError):
    """Errors that indicate operation can be retried."""
    pass

class TransientAPIError(RetryableError):
    """Temporary API failures (500s, timeouts, rate limits)."""

    def __init__(self, message: str, retry_after: int | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
```

## Error Handling Patterns

### 1. Client-Level Error Wrapping

Clients wrap external library exceptions in our custom hierarchy:

```python
class RedditClient(BaseClient):
    def get_post_data(self, link_info: LinkInfo) -> RedditPost:
        try:
            submission = self.reddit.submission(id=link_info.post_id)
            return self._convert_to_post(submission)
        except praw.exceptions.PRAWException as e:
            raise RedditAPIError(
                f"Failed to fetch post: {e}",
                details={"post_id": link_info.post_id}
            ) from e
        except Exception as e:
            raise RedditAPIError(f"Unexpected error: {e}") from e
```

### 2. Service-Level Error Handling

Services catch client errors and may translate or re-raise:

```python
class ContentService:
    def fetch_content(self, url: str) -> RedditPost:
        try:
            link_info = self.parse_url(url)
            return self.reddit_client.get_post_data(link_info)
        except InvalidURLError:
            raise  # Re-raise validation errors as-is
        except RedditAPIError as e:
            logger.error(f"Reddit API error: {e}")
            raise ContentError(f"Could not fetch content: {e}") from e
```

### 3. Workflow-Level Error Handling

The orchestrator handles all exceptions and logs appropriately:

```python
class WorkflowOrchestrator:
    async def process_url(self, url: str) -> WorkflowResult:
        try:
            link_info = self.content_service.parse_url(url)
            post = self.content_service.fetch_content(link_info)
            script = await self.script_service.generate(post)
            media = await self.media_service.create(script)
            result = await self.upload_service.upload(media, script)
            return WorkflowResult(success=True, **result)

        except ValidationError as e:
            self.logger.log_error("Validation failed", error=str(e))
            return WorkflowResult(success=False, error=str(e))

        except APIError as e:
            self.logger.log_error(
                "API error during workflow",
                error_type=type(e).__name__,
                message=str(e),
                status_code=e.status_code
            )
            return WorkflowResult(success=False, error=str(e))

        except RedditFlowError as e:
            self.logger.log_error("Workflow error", error=str(e))
            return WorkflowResult(success=False, error=str(e))

        except Exception as e:
            self.logger.log_error("Unexpected error", error=str(e))
            raise  # Re-raise unexpected errors
```

## Retry Strategy

### RetryConfig

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_interval: float = 1.0
    max_interval: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple = (
        TransientAPIError,
        ConnectionError,
        TimeoutError,
    )
```

### Using Retry Decorator

```python
@with_retry(RetryConfig(max_retries=3))
def call_external_api():
    response = requests.get("https://api.example.com")
    if response.status_code >= 500:
        raise TransientAPIError(
            "Server error",
            status_code=response.status_code
        )
    return response.json()
```

### Circuit Breaker

Prevents cascading failures:

```python
circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0
)

@with_circuit_breaker(circuit_breaker)
def risky_api_call():
    return external_service.call()
```

## Error Response Format

When errors occur, they are logged in structured JSON format:

```json
{
  "timestamp": "2026-01-11T10:30:00Z",
  "level": "ERROR",
  "event": "api_error",
  "error_type": "VideoGenerationError",
  "message": "HeyGen video generation failed",
  "details": {
    "video_id": "abc123",
    "status_code": 500,
    "retry_count": 3
  },
  "workflow_id": "wf_123456"
}
```

## Best Practices

1. **Always chain exceptions** using `raise ... from e` to preserve traceback
2. **Use specific exceptions** rather than catching all `Exception`
3. **Include context** in error details (IDs, URLs, etc.)
4. **Log before raising** at the point closest to the error
5. **Don't swallow errors** - either handle meaningfully or re-raise
6. **Use retryable errors** for transient failures only
7. **Set appropriate timeouts** to prevent hung operations
