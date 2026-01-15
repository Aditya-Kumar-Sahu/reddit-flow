# Reddit-Flow Architecture

**Version:** 1.0
**Last Updated:** January 2026

## Overview

Reddit-Flow is a Python automation system that transforms Reddit discussions into AI-hosted video content and uploads them to YouTube. The system uses a modular, service-oriented architecture with clear separation of concerns.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                             Entry Points                                │
│   ┌────────────────────┐                    ┌────────────────────────┐  │
│   │   Telegram Bot     │                    │      CLI / main.py     │  │
│   │   (bot/handlers)   │                    │   (direct invocation)  │  │
│   └─────────┬──────────┘                    └────────────┬───────────┘  │
│             │                                            │              │
│             └──────────────────┬─────────────────────────┘              │
│                                ▼                                        │
│                   ┌────────────────────────┐                            │
│                   │  WorkflowOrchestrator  │                            │
│                   │  (services/workflow)   │                            │
│                   └────────────┬───────────┘                            │
├────────────────────────────────┼────────────────────────────────────────┤
│                                │                        Service Layer   │
│     ┌────────────┬─────────────┼──────────────┬─────────────┐           │
│     │            │             │              │             │           │
│     ▼            ▼             ▼              ▼             ▼           │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐     │
│ │ Content  │ │ Script   │ │  Media   │ │ Upload   │ │ Structured  │     │
│ │ Service  │ │ Service  │ │ Service  │ │ Service  │ │   Logger    │     │
│ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────────────┘     │
├──────┼────────────┼────────────┼────────────┼───────────────────────────┤
│      │            │            │            │            Client Layer   │
│      │            │            │            └────────────┐              │
|      │            │            │                         │              │
│      ▼            ▼            ▼                         ▼              │
│ ┌─────────┐ ┌─────────┐ ┌────────────┐ ┌─────────┐ ┌───────────┐        │
│ │ Reddit  │ │ Gemini  │ │ ElevenLabs │ │ HeyGen  │ │  YouTube  │        │
│ │ Client  │ │ Client  │ │   Client   │ │ Client  │ │  Client   │        │
│ └────┬────┘ └────┬────┘ └────┬───────┘ └───┬─────┘ └─────┬─────┘        │
├──────┼───────────┼───────────┼─────────────┼─────────────┼──────────────┤
│      │           │           │             │             │    External  │
│      ▼           ▼           ▼             ▼             ▼        APIs  │
│  [Reddit]    [Gemini]   [ElevenLabs]   [HeyGen]      [YouTube]          │
│    API        AI API      TTS API      Video API    Data API v3         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Package Structure

```
reddit_flow/
├── __init__.py              # Package exports
├── bot/
│   ├── handlers.py          # Telegram command handlers
│   └── workflow.py          # Bot-specific workflow logic
├── clients/
│   ├── base.py              # Abstract base client (BaseClient)
│   ├── reddit_client.py     # Reddit API via PRAW
│   ├── gemini_client.py     # Google Gemini AI
│   ├── elevenlabs_client.py # ElevenLabs TTS
│   ├── heygen_client.py     # HeyGen video generation
│   └── youtube_client.py    # YouTube Data API v3
├── config/
│   ├── settings.py          # Pydantic-based settings
│   └── logging_config.py    # Centralized logging setup
├── exceptions/
│   └── errors.py            # Custom exception hierarchy
├── models/
│   ├── reddit.py            # RedditPost, RedditComment, LinkInfo
│   ├── script.py            # VideoScript, ScriptSection
│   └── video.py             # VideoRequest, AudioAsset, YouTubeUpload*
├── services/
│   ├── content_service.py   # URL parsing, Reddit content fetching
│   ├── script_service.py    # AI script generation
│   ├── media_service.py     # TTS and video generation
│   ├── upload_service.py    # YouTube upload logic
│   └── workflow_orchestrator.py  # Main workflow coordination
└── utils/
    ├── retry.py             # Retry, CircuitBreaker, Timeout
    ├── structured_logger.py # JSON logging utility
    └── validators.py        # URL and input validation
```

## Component Details

### 1. Clients Layer

All clients inherit from `BaseClient` which provides:
- Common initialization pattern
- Health check (`verify_service()`)
- Logging integration
- Abstract method enforcement

| Client | External API | Key Methods |
|--------|--------------|-------------|
| `RedditClient` | Reddit (PRAW) | `get_post_data()`, `get_hot_posts()` |
| `GeminiClient` | Google Gemini AI | `generate_script()`, `extract_link_info()` |
| `ElevenLabsClient` | ElevenLabs TTS | `text_to_speech()`, `list_voices()` |
| `HeyGenClient` | HeyGen v2 API | `generate_video()`, `wait_for_video()` |
| `YouTubeClient` | YouTube Data API | `upload_video()`, `get_channel_info()` |

### 2. Services Layer

Services orchestrate business logic using one or more clients:

| Service | Purpose | Dependencies |
|---------|---------|--------------|
| `ContentService` | Parse URLs, fetch Reddit content | `RedditClient` |
| `ScriptService` | Generate AI video scripts | `GeminiClient`, `ContentService` |
| `MediaService` | Create audio/video content | `ElevenLabsClient`, `HeyGenClient` |
| `UploadService` | Upload to YouTube with metadata | `YouTubeClient` |
| `WorkflowOrchestrator` | Coordinate full workflow | All services |

### 3. Models Layer

Pydantic models ensure type safety and validation:

```python
# Reddit models
RedditPost     # Post with title, content, comments
RedditComment  # Individual comment with author, votes
LinkInfo       # Parsed URL components

# Script models
VideoScript    # Complete script with sections
ScriptSection  # Individual script segment

# Video models
VideoRequest           # HeyGen video generation request
AudioAsset             # Uploaded audio metadata
VideoGenerationResponse # HeyGen response
YouTubeUploadRequest   # YouTube upload parameters
YouTubeUploadResponse  # Upload result with video URL
```

### 4. Error Handling

Exception hierarchy:

```
RedditFlowError (base)
├── ConfigurationError      # Missing/invalid config
├── ValidationError         # Input validation failed
├── InvalidURLError         # Malformed Reddit URL
├── ContentError            # Content processing issues
├── APIError (base)
│   ├── RedditAPIError
│   ├── AIGenerationError
│   ├── TTSError
│   ├── VideoGenerationError
│   └── YouTubeUploadError
├── RetryableError
│   └── TransientAPIError   # Temporary failures
└── MediaGenerationError    # Audio/video creation failed
```

### 5. Resilience Patterns

The `utils/retry.py` module provides:

- **RetryConfig**: Configurable retry behavior with exponential backoff
- **with_retry()**: Decorator for automatic retries
- **CircuitBreaker**: Prevents cascading failures
- **with_timeout()**: Function execution timeouts

## Data Flow

### Full Workflow (URL → YouTube)

```
1. Parse URL
   Input: Reddit URL string
   Output: LinkInfo(subreddit, post_id)

2. Fetch Content
   Input: LinkInfo
   Output: RedditPost(title, content, comments[])

3. Generate Script
   Input: RedditPost + optional user_opinion
   Output: VideoScript(title, body, sections[])

4. Generate Media
   Input: VideoScript
   Steps:
     a. text_to_speech(script.body) → audio_bytes
     b. upload_audio(audio_bytes) → AudioAsset
     c. generate_video(audio_url) → video_id
     d. wait_for_video(video_id) → video_url
   Output: MediaGenerationResult(video_url, audio_asset)

5. Upload Video
   Input: video_url + VideoScript
   Steps:
     a. Download video from HeyGen
     b. Build YouTube metadata
     c. Upload via YouTube API
   Output: UploadResult(youtube_url, video_id)
```

## Configuration

Settings are loaded via Pydantic from environment variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
GOOGLE_API_KEY=...          # Gemini AI
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
HEYGEN_API_KEY=...
HEYGEN_AVATAR_ID=...
YOUTUBE_CLIENT_SECRETS_FILE=youtube-client.json

# Optional
LOG_LEVEL=INFO
LOG_DIR=logs
HEYGEN_VIDEO_WIDTH=1080
HEYGEN_VIDEO_HEIGHT=1920
```

## Testing Strategy

```
tests/
├── unit/           # 625 tests - Mocked dependencies
├── integration/    # 22 tests - Real API calls (skipped if no creds)
└── e2e/            # 13 tests - Full workflow with mocked APIs
```

**Coverage:** 93%+ across all modules

**Markers:**
- `@pytest.mark.unit` - Fast, isolated tests
- `@pytest.mark.integration` - Requires API credentials
- `@pytest.mark.e2e` - Full workflow tests
- `@pytest.mark.slow` - Tests taking >10s
- `@pytest.mark.costly` - Consumes API quota

## Deployment

### Prerequisites
- Python 3.11+
- API credentials for all services
- YouTube OAuth credentials (token.json)

### Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/unit/ -v

# Run with Telegram bot
python main.py

# Script-only mode (no video)
python -c "from reddit_flow import WorkflowOrchestrator; ..."
```

## Design Decisions

1. **Async/Await**: Gemini client and workflow orchestrator use async for better concurrency during API waits.

2. **Pydantic v2**: All models use Pydantic for validation, serialization, and IDE support.

3. **No ORM**: Direct API calls with retry logic instead of database persistence.

4. **Circuit Breaker**: Protects against cascading failures when external APIs are down.

5. **Structured Logging**: JSON logs for production, colored console for development.
