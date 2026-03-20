# Reddit-Flow

Reddit-Flow is a source-agnostic social content pipeline that turns inbound links into AI-generated videos, exports, and channel responses.

The project started as a `Reddit -> YouTube -> Telegram` bot and now supports a broader pipeline:

`source ingestion -> canonical content -> script -> voice/video -> publishers -> messaging channels`

## What It Supports

- Sources: Reddit, Medium articles, Medium feeds
- Script providers: Gemini, OpenAI adapter, Anthropic adapter
- Voice providers: ElevenLabs, OpenAI TTS adapter, Google Cloud TTS adapter
- Video providers: HeyGen, Tavus adapter
- Publishing: YouTube, Instagram direct publish, Instagram export bundles
- Messaging channels: Telegram, WhatsApp webhook/channel adapters

## Current Defaults

- Reddit remains the default source
- Telegram remains the default inbound channel
- YouTube remains the default destination
- Gemini, ElevenLabs, and HeyGen remain the default AI path until alternatives are selected

## Quick Start

### 1. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Fill in the required credentials in `.env`.

### 4. Run the Telegram bot

```bash
python main.py
```

## Core Pipeline

### Legacy flow

- Telegram receives a Reddit URL
- The orchestrator resolves the Reddit source
- Script, media, and publish services generate a YouTube upload
- Telegram sends progress updates and the final link

### Generic flow

- `WorkflowOrchestrator.process_request(...)` accepts a `PipelineRequest`
- Source adapters map incoming content into a canonical `ContentItem`
- Script and media services select target-aware behavior such as `youtube_video` or `instagram_reel`
- Publisher adapters fan the result out to one or more destinations
- Messaging channels convert pipeline events into user-facing updates

## Configuration Highlights

See [.env.example](reddit-flow/.env.example) for the full list.

### Required base credentials

- `TELEGRAM_BOT_TOKEN`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `REDDIT_USERNAME`
- `REDDIT_PASSWORD`
- `GOOGLE_API_KEY`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `HEYGEN_API_KEY`
- `HEYGEN_AVATAR_ID`
- `YOUTUBE_CLIENT_SECRETS_FILE`

### Multi-platform feature flags

- `ENABLE_MEDIUM`
- `ENABLE_INSTAGRAM_PUBLISH`
- `ENABLE_INSTAGRAM_EXPORT`
- `ENABLE_WHATSAPP`
- `ENABLE_PROVIDER_FALLBACKS`

### Provider selection

- `DEFAULT_SCRIPT_PROVIDER`
- `DEFAULT_VOICE_PROVIDER`
- `DEFAULT_VIDEO_PROVIDER`
- `SCRIPT_PROVIDER_FALLBACKS`
- `VOICE_PROVIDER_FALLBACKS`
- `VIDEO_PROVIDER_FALLBACKS`

### Meta-related settings

- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_VERIFY_TOKEN`

### Live integration inputs

- `LIVE_MEDIUM_ARTICLE_URL`
- `LIVE_MEDIUM_FEED_URL`
- `LIVE_INSTAGRAM_MEDIA_URL`

## Testing

### Fast validation

```bash
pytest tests/unit -q
pytest tests/e2e -m e2e -q
mypy reddit_flow
```

### Live integration smoke tests

These are opt-in and credential-gated.

```bash
pytest tests/integration/test_phase6_live_integrations.py -m "integration and live" -q
```

### Existing integration suite

```bash
pytest tests/integration -m integration -q
```

Note: the repository currently has a known ElevenLabs credential-dependent integration failure in some environments. That baseline issue is tracked in `REFACTOR.md`.

## Repository Map

- [main.py](main.py): Telegram bot entrypoint
- [reddit_flow/services/workflow_orchestrator.py](reddit-flow/reddit_flow/services/workflow_orchestrator.py): generic and legacy orchestration
- [reddit_flow/pipeline](reddit-flow/reddit_flow/pipeline): source, provider, and publisher abstractions
- [reddit_flow/channels](reddit-flow/reddit_flow/channels): Telegram and WhatsApp channel adapters
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system architecture
- [docs/DEVELOPER_SETUP.md](docs/DEVELOPER_SETUP.md): local setup and workflow
- [docs/ONBOARDING.md](docs/ONBOARDING.md): contributor onboarding

## Notes

- Instagram direct publishing is feature-gated and still built around an injected client contract.
- WhatsApp support currently focuses on webhook verification, link intake, progress updates, and final delivery messages.
- `REFACTOR.md` is the active migration tracker for this multi-platform refactor.
