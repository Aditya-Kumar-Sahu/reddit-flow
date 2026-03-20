# Reddit-Flow Architecture

## Overview

Reddit-Flow now centers on a canonical multi-platform pipeline instead of a Reddit-only workflow.

The key design choice is that sources, providers, publishers, and messaging channels all plug into the same orchestrator through small contracts.

```text
Inbound Channel
    ->
PipelineRequest
    ->
SourceAdapter
    ->
ContentItem
    ->
ScriptService
    ->
MediaService
    ->
Publisher(s)
    ->
PipelineResult + PipelineEvent(s)
    ->
Outbound Channel
```

## Main Runtime Pieces

### Entry points

- `main.py` starts the Telegram bot
- `TelegramChannel` handles Telegram messages and forwards them into the orchestrator
- `WhatsAppChannel` handles webhook-delivered text input and returns progress/final messages

### Orchestration

- `WorkflowOrchestrator.process_request(...)` is the generic pipeline entry point
- `WorkflowOrchestrator.process_reddit_url(...)` remains as the legacy compatibility path
- The orchestrator emits channel-neutral `PipelineEvent` objects throughout execution

### Canonical models

- `PipelineRequest`: normalized input for any supported workflow
- `ContentItem`: canonical content from Reddit, Medium, or future sources
- `PipelineResult`: final workflow outcome across destinations
- `PublishRequest` and `PublishResult`: normalized publish contracts
- `ChannelSpec` and `DestinationSpec`: channel and publish context

## Adapters and Registries

### Sources

- `RedditSourceAdapter`
- `MediumArticleSourceAdapter`
- `MediumFeedSourceAdapter`

These are resolved by `SourceAdapterRegistry`.

### Providers

- Script: Gemini, OpenAI adapter, Anthropic adapter
- Voice: ElevenLabs, OpenAI TTS adapter, Google Cloud TTS adapter
- Video: HeyGen, Tavus adapter

These are resolved by `ProviderRegistry`.

### Publishers

- `YouTubePublisher`
- `InstagramPublisher`

Instagram publishing always creates an export bundle and optionally performs a direct publish when enabled.

### Channels

- `TelegramChannel`
- `WhatsAppChannel`

Channels convert inbound user input into `PipelineRequest` objects and translate `PipelineEvent` updates back into human-readable status messages.

## Destination-Aware Behavior

The generic pipeline now chooses target-specific script and media behavior from the destination list.

- YouTube defaults to `youtube_video`
- Instagram uses `instagram_reel`
- Messaging-focused summaries can use `messaging_summary`

This target is passed into both script generation and media rendering so the same source content can be shaped differently per destination.

## Logging

Phase 6 adds structured pipeline context to orchestrator logs.

Every important pipeline state can now include:

- `workflow_id`
- `source_type`
- `target_destinations`
- `channel`
- `provider_path`
- `partial_content`

This is designed for JSON log sinks through the existing logging configuration.

## Testing Strategy

### Unit tests

- Validate models, contracts, services, adapters, and failure paths
- Cover provider fallback, media timeouts, publish failures, and channel cleanup behavior

### End-to-end tests

- Keep the legacy `Reddit -> YouTube -> Telegram` path green
- Verify `Medium article -> Instagram -> WhatsApp`
- Verify `Medium feed -> Instagram export bundle -> WhatsApp`

### Live integration smoke tests

- Medium article fetch
- Medium feed fetch
- Gemini script generation from live Medium content
- Credential-gated Instagram and WhatsApp contract smoke checks

## Compatibility Notes

- The internal bot entrypoint now uses `TelegramChannel` directly
- Legacy compatibility wrappers remain only where they reduce migration risk
- `REFACTOR.md` tracks the remaining cleanup items and any deferred compatibility removal
