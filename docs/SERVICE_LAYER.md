# Service Layer Architecture

This document describes the service layer design and how services interact.

## Overview

The service layer sits between the entry points (Telegram bot, CLI) and the client layer (API integrations). Services encapsulate business logic and coordinate between multiple clients.

```
Entry Points ─────▶ Services ─────▶ Clients ─────▶ External APIs
```

## Services

### ContentService

**Purpose:** Parse Reddit URLs and fetch content.

**Location:** `reddit_flow/services/content_service.py`

**Dependencies:**
- `RedditClient` - For fetching post data
- `validators` - For URL validation

**Methods:**

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `parse_url()` | `str` (URL) | `LinkInfo` | Extract subreddit and post ID from URL |
| `fetch_content()` | `LinkInfo` | `RedditPost` | Get full post with comments |
| `fetch_by_url()` | `str` (URL) | `RedditPost` | Convenience: parse + fetch in one call |

**Usage:**
```python
content_service = ContentService(reddit_client)

# Parse URL to get metadata
link_info = content_service.parse_url(
    "https://reddit.com/r/Python/comments/abc123/title"
)
# LinkInfo(subreddit="Python", post_id="abc123")

# Fetch full content
post = content_service.fetch_content(link_info)
# RedditPost(title="...", body="...", comments=[...])
```

---

### ScriptService

**Purpose:** Generate AI video scripts from Reddit content.

**Location:** `reddit_flow/services/script_service.py`

**Dependencies:**
- `GeminiClient` - For AI text generation
- `ContentService` - To fetch content if needed

**Methods:**

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `generate_script()` | `RedditPost`, `user_opinion?` | `VideoScript` | Create video script |
| `generate_from_url()` | `str` (URL), `user_opinion?` | `VideoScript` | Fetch + generate in one call |

**Usage:**
```python
script_service = ScriptService(gemini_client, content_service)

# Generate script with optional user opinion
script = await script_service.generate_script(
    post=reddit_post,
    user_opinion="I think the top answer is wrong because..."
)
# VideoScript(title="...", body="...", sections=[...])
```

---

### MediaService

**Purpose:** Generate audio and video from scripts.

**Location:** `reddit_flow/services/media_service.py`

**Dependencies:**
- `ElevenLabsClient` - For text-to-speech
- `HeyGenClient` - For avatar video generation

**Methods:**

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `generate_audio()` | `str` (text) | `bytes` | Convert text to speech |
| `upload_audio()` | `bytes` | `AudioAsset` | Upload audio to HeyGen |
| `generate_video()` | `VideoScript` | `MediaResult` | Full audio→video pipeline |

**Usage:**
```python
media_service = MediaService(elevenlabs_client, heygen_client)

# Full pipeline
result = await media_service.generate_video(script)
# MediaResult(
#     video_url="https://heygen.com/videos/xyz",
#     audio_asset=AudioAsset(asset_id="...", url="...")
# )
```

**Pipeline Flow:**
```
     VideoScript
          │
          ▼
┌──────────────────┐
│ text_to_speech() │  ElevenLabs
└─────────┬────────┘
          │ audio bytes
          ▼
┌──────────────────┐
│  upload_audio()  │  HeyGen
└─────────┬────────┘
          │ AudioAsset
          ▼
┌──────────────────┐
│ generate_video() │  HeyGen
└─────────┬────────┘
          │ video_id
          ▼
┌──────────────────┐
│ wait_for_video() │  HeyGen (polling)
└─────────┬────────┘
          │
          ▼
     MediaResult
```

---

### UploadService

**Purpose:** Upload videos to YouTube with metadata.

**Location:** `reddit_flow/services/upload_service.py`

**Dependencies:**
- `YouTubeClient` - For YouTube Data API

**Methods:**

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `upload()` | `video_url`, `VideoScript` | `UploadResult` | Download & upload to YouTube |
| `build_metadata()` | `VideoScript` | `YouTubeUploadRequest` | Create YouTube metadata |

**Usage:**
```python
upload_service = UploadService(youtube_client)

result = await upload_service.upload(
    video_url="https://heygen.com/videos/xyz",
    script=video_script
)
# UploadResult(
#     youtube_url="https://youtube.com/watch?v=abc",
#     video_id="abc"
# )
```

---

### WorkflowOrchestrator

**Purpose:** Coordinate the entire URL-to-YouTube pipeline.

**Location:** `reddit_flow/services/workflow_orchestrator.py`

**Dependencies:**
- All other services
- `StructuredLogger` - For workflow logging

**Methods:**

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `process_url()` | `str` (URL), options | `WorkflowResult` | Full pipeline |
| `process_with_opinion()` | URL, opinion | `WorkflowResult` | Include user opinion |

**Usage:**
```python
orchestrator = WorkflowOrchestrator(
    content_service=content_service,
    script_service=script_service,
    media_service=media_service,
    upload_service=upload_service,
    logger=structured_logger
)

# Full workflow
result = await orchestrator.process_url(
    url="https://reddit.com/r/Python/comments/abc123/title",
    user_opinion="My thoughts on this topic..."
)

if result.success:
    print(f"Video uploaded: {result.youtube_url}")
else:
    print(f"Failed: {result.error}")
```

## Service Initialization

Services are typically created with dependency injection:

```python
# Initialize clients
reddit_client = RedditClient(settings)
gemini_client = GeminiClient(settings)
elevenlabs_client = ElevenLabsClient(settings)
heygen_client = HeyGenClient(settings)
youtube_client = YouTubeClient(settings)

# Initialize services with clients
content_service = ContentService(reddit_client)
script_service = ScriptService(gemini_client, content_service)
media_service = MediaService(elevenlabs_client, heygen_client)
upload_service = UploadService(youtube_client)

# Create orchestrator with all services
orchestrator = WorkflowOrchestrator(
    content_service=content_service,
    script_service=script_service,
    media_service=media_service,
    upload_service=upload_service
)
```

## Testing Services

Services are tested with mocked client dependencies:

```python
def test_content_service_parse_url():
    mock_reddit = Mock(spec=RedditClient)
    service = ContentService(mock_reddit)

    result = service.parse_url("https://reddit.com/r/test/comments/123/title")

    assert result.subreddit == "test"
    assert result.post_id == "123"

async def test_script_service_generate():
    mock_gemini = AsyncMock(spec=GeminiClient)
    mock_gemini.generate_script.return_value = VideoScript(...)

    service = ScriptService(mock_gemini, mock_content_service)
    result = await service.generate_script(reddit_post)

    mock_gemini.generate_script.assert_called_once()
    assert isinstance(result, VideoScript)
```

## Design Principles

1. **Single Responsibility:** Each service handles one domain area
2. **Dependency Injection:** Services receive clients via constructor
3. **Async Where Needed:** Long-running operations (AI, video) are async
4. **Error Translation:** Services convert client errors to domain errors
5. **Logging:** Services log significant operations for debugging
6. **Testability:** All dependencies are injectable for easy mocking
