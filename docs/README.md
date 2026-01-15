# Reddit-Flow Documentation

Welcome to the reddit-flow technical documentation.

## Documentation Index

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | High-level system architecture, component overview, data flow |
| [MODULE_DEPENDENCIES.md](MODULE_DEPENDENCIES.md) | Module dependency graph and import rules |
| [SERVICE_LAYER.md](SERVICE_LAYER.md) | Service design patterns, API reference, usage examples |
| [EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md) | Error handling strategy, exception hierarchy, best practices |
| [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md) | Development environment setup, testing, code quality |

## Quick Links

- **Getting Started:** See [../README.md](../README.md)
- **Developer Setup:** See [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)
- **API Reference:** See individual module docstrings

## Architecture at a Glance

```
┌────────────────────────────────────────────────────┐
│                  Entry Points                      │
│         (Telegram Bot / CLI / main.py)             │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│               WorkflowOrchestrator                 │
│  (Coordinates: Content → Script → Media → Upload)  │
└────────────────────────┬───────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ ContentSvc   │ │ ScriptSvc    │ │ MediaSvc     │
│ (Reddit)     │ │ (AI/Gemini)  │ │ (TTS/Video)  │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ RedditClient │ │ GeminiClient │ │ ElevenLabs   │
│              │ │              │ │ HeyGenClient │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Key Concepts

### Package Structure
- **`clients/`** - API integrations (Reddit, Gemini, ElevenLabs, HeyGen, YouTube)
- **`services/`** - Business logic layer
- **`models/`** - Pydantic data models
- **`config/`** - Settings and logging configuration
- **`exceptions/`** - Custom exception hierarchy
- **`utils/`** - Retry logic, validators, structured logging

### Data Flow
1. **URL → LinkInfo** - Parse Reddit URL
2. **LinkInfo → RedditPost** - Fetch content with comments
3. **RedditPost → VideoScript** - Generate AI script
4. **VideoScript → MediaResult** - Create audio & video
5. **MediaResult → YouTubeURL** - Upload to YouTube

### Error Handling
All errors inherit from `RedditFlowError`. API errors are retryable with exponential backoff. Circuit breaker prevents cascading failures.

## Testing

```bash
# Run unit tests (fast, mocked)
pytest tests/unit/ -v

# Run E2E tests (mocked APIs)
pytest tests/e2e/ -v

# Run integration tests (requires API keys)
pytest tests/integration/ -v --run-integration

# Run all tests with coverage
pytest --cov=reddit_flow --cov-report=html
```

## Contributing

1. Follow the layer isolation rules in [MODULE_DEPENDENCIES.md](MODULE_DEPENDENCIES.md)
2. Use the exception patterns from [EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md)
3. Write tests for all new code
4. Run `mypy` and ensure 0 errors
5. Maintain docstring coverage
