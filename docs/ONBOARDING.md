# Onboarding

## Read This First

Start with these files in order:

1. [README.md](../README.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)
4. [REFACTOR.md](../REFACTOR.md)

## Mental Model

Think of the system as a pipeline with pluggable edges:

- A channel receives user input
- A source adapter turns it into a canonical content model
- Script and media services generate the asset
- Publisher adapters fan that asset out to destinations
- The channel reports progress and final results back to the user

## Most Important Code Paths

- `reddit_flow/services/workflow_orchestrator.py`
- `reddit_flow/pipeline/sources.py`
- `reddit_flow/services/script_service.py`
- `reddit_flow/services/media_service.py`
- `reddit_flow/pipeline/publishers.py`
- `reddit_flow/channels/telegram_channel.py`
- `reddit_flow/channels/whatsapp_channel.py`

## How To Add Something New

### New source

- Add a source adapter under `reddit_flow/pipeline/`
- Map the source into `ContentItem`
- Add unit tests and a mocked e2e path if it changes workflow behavior

### New provider

- Add an adapter under `reddit_flow/pipeline/providers.py` or a nearby module
- Register it through `ProviderRegistry`
- Add fallback coverage and failure-path tests

### New destination

- Add a publisher adapter
- Decide whether the destination needs export-only support, direct publish, or both
- Update channel completion messages if new artifact types are produced

### New channel

- Convert inbound input into `PipelineRequest`
- Surface `PipelineEvent` progress clearly
- Add duplicate-job protection and cleanup tests

## Testing Priorities

- Keep `Reddit -> YouTube -> Telegram` green at all times
- Prefer unit tests for new branches and adapters
- Add e2e coverage whenever the user-visible workflow changes
- Use live integration tests only when the required credentials or opt-in URLs are present
