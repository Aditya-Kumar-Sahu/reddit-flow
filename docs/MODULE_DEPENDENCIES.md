# Module Dependencies

This document outlines the dependencies between modules in the reddit-flow package.

## Dependency Graph

```
                                    ┌─────────────────┐
                                    │     main.py     │
                                    └────────┬────────┘
                                             │
           ┌─────────────────────────────────┼──────────────────────────────┐
           │                                 │                              │
           ▼                                 ▼                              ▼
    ┌─────────────┐              ┌───────────────────────┐           ┌─────────────┐
    │   bot/      │              │  services/            │           │   config/   │
    │  handlers   │──────────────│  workflow_orchestrator│───────────│  settings   │
    │  workflow   │              │                       │           │  logging    │
    └─────────────┘              └───────────┬───────────┘           └─────────────┘
                                             │
              ┌──────────────────────────────┼───────────────────────────┐
              │                              │                           │
              ▼                              ▼                           ▼
    ┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
    │  services/          │      │  services/          │      │  services/          │
    │  content_service    │      │  script_service     │      │  media_service      │
    │                     │      │                     │      │                     │
    │  - url parsing      │      │  - AI generation    │      │  - TTS              │
    │  - Reddit fetching  │      │  - script creation  │      │  - video generation │
    └──────────┬──────────┘      └──────────┬──────────┘      └──────────┬──────────┘
               │                            │                            │
    ┌──────────┼─────────┐       ┌──────────┼──────────┐      ┌──────────┼──────────┐
    │          │         │       │          │          │      │          │          │
    ▼          ▼         ▼       ▼          ▼          ▼      ▼          ▼          ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│models/│ │utils/ │ │clients│ │models/│ │utils/ │ │clients│ │models/│ │utils/ │ │clients│
│reddit │ │valid. │ │reddit │ │script │ │retry  │ │gemini │ │video  │ │retry  │ │eleven │
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘ │heygen │
                                                                                └───────┘

Legend:
───────► Depends on
```

## Detailed Dependencies

### Core Services

| Module | Direct Dependencies |
|--------|---------------------|
| `workflow_orchestrator` | `content_service`, `script_service`, `media_service`, `upload_service`, `structured_logger`, all models |
| `content_service` | `reddit_client`, `validators`, `LinkInfo`, `RedditPost` |
| `script_service` | `gemini_client`, `content_service`, `VideoScript` |
| `media_service` | `elevenlabs_client`, `heygen_client`, `VideoRequest`, `AudioAsset` |
| `upload_service` | `youtube_client`, `YouTubeUploadRequest`, `YouTubeUploadResponse` |

### Clients

| Client | Direct Dependencies |
|--------|---------------------|
| `base.py` | `settings`, `logging_config`, `errors` |
| `reddit_client` | `base.py`, `RedditPost`, `RedditComment`, `RetryConfig`, `with_retry` |
| `gemini_client` | `base.py`, `VideoScript`, `LinkInfo`, `with_retry` |
| `elevenlabs_client` | `base.py`, `with_retry`, `CircuitBreaker` |
| `heygen_client` | `base.py`, `VideoRequest`, `VideoGenerationResponse`, `with_retry` |
| `youtube_client` | `base.py`, `YouTubeUploadRequest`, `YouTubeUploadResponse` |

### Models

| Model File | Contains |
|------------|----------|
| `reddit.py` | `RedditComment`, `RedditPost`, `LinkInfo` |
| `script.py` | `ScriptSection`, `VideoScript` |
| `video.py` | `VideoRequest`, `AudioAsset`, `VideoGenerationResponse`, `YouTubeUploadRequest`, `YouTubeUploadResponse` |

### Utils

| Utility | Used By |
|---------|---------|
| `retry.py` | All clients, `media_service` |
| `validators.py` | `content_service`, `bot/handlers` |
| `structured_logger.py` | `workflow_orchestrator`, main entry points |

## Import Rules

1. **Models have no dependencies** (except Pydantic and standard library)
2. **Utils depend only on models and config**
3. **Clients depend on base, models, utils, config, and exceptions**
4. **Services depend on clients, models, and utils**
5. **Workflow orchestrator coordinates all services**
6. **No circular dependencies**

## Layer Isolation

```
Layer 4: Entry Points (main.py, bot/)
    │
    │ imports
    ▼
Layer 3: Services (workflow_orchestrator, content_service, etc.)
    │
    │ imports
    ▼
Layer 2: Clients (reddit_client, gemini_client, etc.)
    │
    │ imports
    ▼
Layer 1: Foundation (models/, utils/, config/, exceptions/)
```

Each layer can only import from layers below it, never above.
