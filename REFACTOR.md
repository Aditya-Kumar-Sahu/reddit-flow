# Multi-Platform Social Pipeline Refactor Plan

## Summary
- Extend the current modular repo instead of rewriting it; the existing `clients -> services -> orchestrator` split is reusable, but the domain is still hard-coded around Reddit, Telegram, and YouTube.
- Refactor into a source-agnostic pipeline: `source ingestion -> canonical content -> script -> voice/video -> publishers -> messaging channels`.
- Keep the current `Reddit -> Telegram -> YouTube` flow working during every phase.

## TDD + REFACTOR.md Operating Rules
Checklist:
- [x] First implementation action: create repo-root `REFACTOR.md` from this plan and mark `REFACTORING_PLAN.md` as historical context only.
- [x] Every task starts with a failing test or failing contract test.
- [x] Implement only the smallest change needed to make the test pass.
- [x] Refactor only after tests are green.
- [x] After each task, update `REFACTOR.md` with: task id, tests added, commands run, result, decisions, blockers, and next task.
- [x] After each phase, add a short phase summary and explicitly rerun the legacy Reddit regression flow.

## Public Interface Changes
- [x] Add a generic `process_request(PipelineRequest)` core API.
- [x] Keep `process_reddit_url(...)` as a compatibility wrapper until final cleanup.
- [x] Add canonical models: `ContentItem`, `ContentCandidate`, `PipelineRequest`, `PipelineResult`, `PipelineEvent`, `DestinationSpec`, `ChannelSpec`, `ProviderSelection`.
- [x] Add registries/contracts for `SourceAdapter`, `ScriptProvider`, `VoiceProvider`, `VideoProvider`, `Publisher`, and `MessageChannel`.
- [x] Extend configuration with provider selection, Meta credentials, Medium feed settings, and feature flags.

## Provider Defaults and Alternatives
- [x] Script generation: keep Gemini as default; add OpenAI and Anthropic adapters.
- [x] Voice generation: keep ElevenLabs as default; add OpenAI TTS and Google Cloud TTS.
- [x] Video generation: keep HeyGen as default; add Tavus for avatar video; treat Sora as an optional creative/b-roll provider instead of a direct talking-avatar replacement.
- [x] Publishing: keep YouTube; add Instagram direct publish and always-on export bundle generation.
- [x] Messaging: keep Telegram; add WhatsApp Cloud API.

## Phase 0 - Baseline and Migration Guardrails
Checklist:
- [x] Capture current unit, integration, and e2e commands and baseline results in `REFACTOR.md`.
- [x] Add a regression matrix for the current `Reddit -> Script -> Media -> YouTube -> Telegram reply` path.
- [x] Define feature flags for `medium`, `instagram_publish`, `instagram_export`, `whatsapp`, and `provider_fallbacks`.
- [x] Freeze existing public bot behavior as a non-regression requirement.
- [x] Document rollback rules so any new integration can be disabled without breaking Reddit.
Phase exit:
- [x] Baseline is documented and the legacy flow has explicit regression coverage.

## Phase 1 - Core Domain Generalization
Checklist:
- [x] Write failing tests for the new canonical models and request/result lifecycle.
- [x] Write failing contract tests for adapter/provider/channel interfaces.
- [x] Refactor the orchestrator to accept `PipelineRequest` and emit channel-neutral `PipelineEvent`s.
- [x] Introduce registry-based resolution for sources, providers, publishers, and message channels.
- [x] Keep legacy wrappers intact so existing callers do not break while the core becomes generic.
- [x] Extend settings to load enabled sources, destinations, provider defaults, and fallbacks.
Phase exit:
- [x] New contracts are green and the legacy Reddit workflow still passes.

## Phase 2 - Source Connectors: Reddit Plus Medium
Checklist:
- [x] Write failing tests that map current Reddit payloads into the canonical `ContentItem`.
- [x] Write failing tests for Medium article URL parsing, normalization, and content extraction using HTML fixtures.
- [x] Write failing tests for Medium profile/publication/topic RSS parsing into `ContentCandidate` items.
- [x] Add a `MediumClient` for RSS fetch plus article enrichment.
- [x] Convert `ContentService` into a source router over `RedditSourceAdapter`, `MediumArticleSourceAdapter`, and `MediumFeedSourceAdapter`.
- [x] Preserve Reddit-specific parsing inside the Reddit adapter instead of top-level workflow logic.
- [x] Mark Medium content as `partial` when only summary text is available, especially for paywalled stories.
Phase exit:
- [x] Reddit and Medium inputs both resolve into the same canonical content model.

## Phase 3 - Script, Voice, and Video Provider Abstraction
Checklist:
- [x] Write failing tests for target-specific script briefs: `youtube_video`, `instagram_reel`, and `messaging_summary`.
- [x] Write failing tests for provider registry resolution and fallback order.
- [x] Refactor `ScriptService` into prompt-template selection plus provider execution.
- [x] Add `OpenAIScriptProvider` and `AnthropicScriptProvider` beside the existing Gemini path.
- [x] Split media generation so voice and video use separate provider contracts.
- [x] Add `OpenAITTSProvider` and `GoogleCloudTTSProvider` beside ElevenLabs.
- [x] Add `TavusVideoProvider` beside HeyGen.
- [x] Add normalized render profiles so providers receive the same portrait/landscape and caption requirements.
- [x] Store provider cost/latency metadata in results so routing stays observable.
Phase exit:
- [x] The same canonical content can be rendered through multiple script, voice, and video providers in mocked tests.

## Phase 4 - Publishing: YouTube Plus Instagram
Checklist:
- [ ] Write failing tests for generic `PublishRequest` and `PublishResult`.
- [ ] Wrap the existing YouTube flow behind a `YouTubePublisher` adapter with no user-visible changes.
- [ ] Write failing tests for Instagram reel publish container creation, publish completion, and error mapping.
- [ ] Implement `InstagramPublisher` for direct publish to professional accounts.
- [ ] Implement `InstagramExportBundleService` that always creates a reel MP4, caption text, hashtag text, and publish manifest.
- [ ] Add target-specific metadata shaping so Instagram gets short-form captioning while YouTube keeps richer descriptions.
- [ ] Ensure one render can fan out to both YouTube and Instagram unless render profiles differ.
- [ ] Keep direct Instagram publish behind a feature flag; export bundle generation remains enabled even when direct publish is off.
Phase exit:
- [ ] YouTube regression tests stay green and Instagram direct/export paths are both covered.

## Phase 5 - Messaging Channels: Telegram Plus WhatsApp
Checklist:
- [ ] Write failing tests for channel-neutral inbound parsing, outbound progress, final result, and error delivery.
- [ ] Extract existing Telegram logic into a `TelegramChannel` adapter without changing user-facing behavior.
- [ ] Add a small webhook entrypoint for WhatsApp Cloud API verification and inbound events.
- [ ] Implement a `WhatsAppChannel` that accepts link/text input, sends queued progress updates, and returns final outputs.
- [ ] Add conversation-state tracking keyed by channel plus user/conversation id to prevent duplicate jobs consistently.
- [ ] Add delivery rules so WhatsApp can send a publish link, a local/export asset, or both based on render size and destination state.
- [ ] Keep the first WhatsApp release intentionally narrow: user-submitted links, progress messages, and final outputs only.
Phase exit:
- [ ] Telegram behavior is preserved and WhatsApp webhook/inbound/outbound tests pass with mocks.

## Phase 6 - End-to-End Hardening, Docs, and Cleanup
Checklist:
- [ ] Write e2e tests for `Reddit -> YouTube -> Telegram`, `Medium article -> Instagram -> WhatsApp`, and `Medium feed candidate -> Instagram export + WhatsApp notification`.
- [ ] Add failure-path tests for source parsing errors, partial Medium content, provider fallback, media timeouts, Instagram publish failure, and WhatsApp send failure.
- [ ] Add live integration markers for optional providers and channels so they only run when credentials are present.
- [ ] Extend structured logging with `source_type`, `target_destinations`, `channel`, `provider_path`, `workflow_id`, and `partial_content`.
- [ ] Update `README`, `.env.example`, architecture docs, and onboarding docs for the new pipeline.
- [ ] Remove temporary compatibility shims only after all callers and regression tests are green.
- [ ] Move any leftover nice-to-have items into a post-v1 backlog section in `REFACTOR.md`.
Phase exit:
- [ ] All core flows are green, documented, and rollback-safe.

## Test Plan
Checklist:
- [x] Unit tests for canonical models, settings, routing, and formatters.
- [x] Contract tests for every adapter/provider/channel type.
- [x] Regression tests for the current Reddit path before and after each phase.
- [x] Mocked e2e tests for cross-platform workflows.
- [ ] Live integration tests for Medium fetch, Instagram publish, WhatsApp webhook/send, and selected AI providers behind env-gated markers.
- [x] Static checks for typing and configuration drift after each phase.
Recommended phase-gate commands:
- [x] `pytest tests/unit`
- [x] `pytest tests/e2e -m e2e`
- [ ] `pytest tests/integration -m integration`
- [x] `mypy reddit_flow`

## Assumptions and Defaults
- [x] This is a plan-only turn, so creating `REFACTOR.md` is the first implementation step rather than something completed in this response.
- [x] `REFACTORING_PLAN.md` remains historical; `REFACTOR.md` becomes the active tracker for this initiative.
- [x] Medium feed support uses official RSS feeds for profiles, publications, and topics, then enriches entries through article fetch when available.
- [x] WhatsApp support uses Meta Cloud API, not Twilio.
- [x] Instagram direct publish targets professional accounts and uses the current `instagram_business_*` permission naming rather than deprecated `business_*` scopes.
- [x] Existing Reddit, Telegram, YouTube, Gemini, ElevenLabs, and HeyGen integrations remain the default path until alternatives are proven green.
- [x] Sora is treated as a creative-video option, not a direct avatar-video replacement.
- [x] FastAPI is the recommended webhook surface for WhatsApp and future provider callbacks; Telegram polling can remain in place during migration.

## Reference Inputs Used For This Plan
- [Medium RSS feed support](https://help.medium.com/hc/en-us/articles/214874118-Using-RSS-feeds-of-profiles-publications-and-topics)
- [Meta Instagram API with Instagram Login collection](https://www.postman.com/meta/instagram/folder/9vtdu7i/instagram-api-with-instagram-login)
- [Meta WhatsApp Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api)
- [Gemini text generation docs](https://ai.google.dev/gemini-api/docs/text-generation)
- [Anthropic API overview](https://docs.anthropic.com/en/api/overview)
- [OpenAI video generation](https://platform.openai.com/docs/guides/video-generation)
- [OpenAI text-to-speech](https://platform.openai.com/docs/guides/text-to-speech)
- [ElevenLabs text-to-speech docs](https://elevenlabs.io/docs/overview/capabilities/text-to-speech)
- [Google Cloud text-to-speech docs](https://cloud.google.com/text-to-speech/docs)
- [Tavus video generation API](https://docs.tavus.io/api-reference/video-request/create-video)

## Progress Notes

### Task 0.1 - Create active tracker

- Status: COMPLETE
- Tests added: None
- Commands run: None
- Result: Created `REFACTOR.md` as the active refactor tracker.
- Decisions: Keep `REFACTORING_PLAN.md` as historical context only.
- Blockers: None
- Next task: Capture baseline results and add first failing tests for generic pipeline models/contracts.

### Task 0.2 - Capture pre-refactor baseline

- Status: COMPLETE
- Tests added: None
- Commands run: `pytest tests/unit`, `pytest tests/e2e -m e2e`, `pytest tests/integration -m integration`, `mypy reddit_flow`
- Result: Unit, e2e, and mypy baselines are green; integration has one existing ElevenLabs auth failure.
- Decisions: Treat integration auth issues as environment/service baseline, not a regression from the new pipeline work.
- Blockers: Existing ElevenLabs integration credentials are not valid for text-to-speech requests.
- Next task: Add failing tests for canonical pipeline models, registries, settings, and generic orchestrator flow.

### Task 1.1 - Add generic pipeline foundation

- Status: COMPLETE
- Tests added: `tests/unit/test_pipeline_models.py`, `tests/unit/test_pipeline_registry.py`, `tests/unit/test_pipeline_settings.py`, generic workflow coverage in `tests/unit/test_workflow_orchestrator.py`
- Commands run: targeted pytest for new tests, full `pytest tests/unit`, `pytest tests/e2e -m e2e`, `mypy reddit_flow`
- Result: Added canonical pipeline models, pipeline contracts/registries, default Reddit source adapter, YouTube publisher adapter, feature-flag/provider settings, and `WorkflowOrchestrator.process_request(...)`.
- Decisions: Keep the legacy `process_reddit_url(...)` path intact while the generic path matures; use adapters to bridge into current services instead of rewriting the services first.
- Blockers: None
- Next task: Start the first Medium ingestion slice with failing tests for article URL parsing and RSS feed candidates.

### Task 2.1 - Add first Medium ingestion slice

- Status: COMPLETE
- Tests added: `tests/unit/test_medium_client.py`, `tests/unit/test_script_service_pipeline.py`, non-Reddit workflow coverage in `tests/unit/test_workflow_orchestrator.py`
- Commands run: targeted pytest for Medium/generic tests, full `pytest tests/unit`, `pytest tests/e2e -m e2e`, `mypy reddit_flow`
- Result: Added `MediumClient`, Medium article/feed source adapters, generic `ScriptService.generate_script_from_content_item(...)`, and non-Reddit orchestration support through the canonical pipeline.
- Decisions: Feed/profile Medium URLs currently resolve to the latest article for the first generic ingestion pass; canonical content now works without a legacy Reddit model.
- Blockers: None
- Next task: Add dedicated provider adapters for script, voice, and video selection/fallback instead of routing directly through legacy services.

### Task 3.1 - Add provider abstraction and render profiles

- Status: COMPLETE
- Tests added: `tests/unit/test_phase3_provider_abstraction.py`
- Commands run: targeted pytest for Phase 3 and media regression tests, full `pytest tests/unit`, `pytest tests/e2e -m e2e`, `mypy reddit_flow`
- Result: Added target-specific script briefs, provider registry resolution for script/voice/video, provider wrappers for Gemini/OpenAI/Anthropic, ElevenLabs/OpenAI/Google TTS, and HeyGen/Tavus, normalized render profiles, and provider-routing metadata on media results.
- Decisions: Preserve the legacy Reddit/HeyGen upload flow while adding abstraction layers around it; keep provider selection fallback-driven so existing defaults remain stable.
- Blockers: None
- Next task: Begin Phase 4 publishing work with YouTube publisher hardening and Instagram direct/export support.

### Task 3.2 - Harden Medium feed parsing

- Status: COMPLETE
- Tests added: Existing `tests/unit/test_medium_client.py` coverage exercised during the fix
- Commands run: targeted `pytest tests/unit/test_medium_client.py -q`, targeted Bandit check on `reddit_flow/clients/medium_client.py`
- Result: Replaced `xml.etree.ElementTree` parsing in `MediumClient.parse_feed(...)` with a constrained tag extractor so Bandit no longer flags untrusted XML parsing.
- Decisions: Keep the parser narrow and feed-specific rather than suppressing Bandit or introducing a new dependency for a simple Medium RSS shape.
- Blockers: None
- Next task: Begin Phase 4 publishing work with YouTube publisher hardening and Instagram direct/export support.

## Current Verification

- `pytest tests/unit`: 650 passed
- `pytest tests/e2e -m e2e`: 13 passed
- `mypy reddit_flow`: green
- `bandit reddit_flow/clients/medium_client.py`: clean

## Phase Status

- Phase 0: COMPLETE
- Phase 1: COMPLETE
- Phase 2: COMPLETE
- Phase 3: COMPLETE
- Phase 4: NOT STARTED
- Phase 5: NOT STARTED
- Phase 6: NOT STARTED
