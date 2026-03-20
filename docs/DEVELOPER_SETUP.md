# Developer Setup

## Local Environment

### 1. Create a virtual environment

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

Set the credentials you need for the surfaces you are working on. Unit and mocked e2e tests run with the test fixture environment and do not require live credentials.

### 4. Install pre-commit hooks

```bash
pre-commit install
```

## Recommended Workflow

### Fast feedback loop

```bash
pytest tests/unit -q
pytest tests/e2e -m e2e -q
mypy reddit_flow
```

### Phase 6 live smoke tests

```bash
pytest tests/integration/test_phase6_live_integrations.py -m "integration and live" -q
```

### Full integration suite

```bash
pytest tests/integration -m integration -q
```

## Where to Work

- `reddit_flow/services/`: orchestration and business logic
- `reddit_flow/pipeline/`: source, provider, and publisher contracts/adapters
- `reddit_flow/channels/`: Telegram and WhatsApp channel logic
- `reddit_flow/clients/`: API clients and transport boundaries
- `tests/unit/`: fast contract and service coverage
- `tests/e2e/`: mocked end-to-end workflows
- `tests/integration/`: credential-gated live smoke tests

## TDD Expectations

- Start with a failing test
- Make the smallest change that turns it green
- Refactor only after the test is green
- Update `REFACTOR.md` after each completed task or phase

## Feature Flags To Know

- `ENABLE_MEDIUM`
- `ENABLE_INSTAGRAM_PUBLISH`
- `ENABLE_INSTAGRAM_EXPORT`
- `ENABLE_WHATSAPP`
- `ENABLE_PROVIDER_FALLBACKS`

## Useful Commands

```bash
# Type checking
mypy reddit_flow

# Full mocked regression pass
pytest tests/unit -q
pytest tests/e2e -m e2e -q

# One focused file
pytest tests/unit/test_phase6_hardening.py -q

# Security checks
bandit -q -r reddit_flow
```

## Notes

- The generic pipeline entry point is `WorkflowOrchestrator.process_request(...)`
- The legacy Reddit wrapper still exists for compatibility
- Telegram is the stable production entrypoint
- WhatsApp support currently targets webhook verification, link intake, progress updates, and final delivery messages
