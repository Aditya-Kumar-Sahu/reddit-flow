# Developer Setup Guide

This guide covers everything you need to start developing on reddit-flow.

## Prerequisites

- **Python 3.11+** (3.9+ minimum)
- **Git** for version control
- **VS Code** (recommended) or your preferred IDE

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd reddit-flow
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
# Install all dependencies (production + development)
pip install -r requirements.txt
```

### 4. Install Pre-commit Hooks

```bash
pre-commit install
```

This enables automatic code formatting and linting on every commit.

### 5. Configure Environment

```bash
# Copy the example environment file
copy .env.example .env  # Windows
cp .env.example .env    # Linux/Mac

# Edit .env with your API credentials
```

## Running the Application

### Start the Telegram Bot

```bash
python main.py
```

### Run Specific Components

```python
# Import and use components directly
from reddit_flow import WorkflowOrchestrator, Settings
from reddit_flow.clients import RedditClient, GeminiClient

settings = Settings()
reddit = RedditClient(settings)
post = reddit.get_post_data(link_info)
```

## Running Tests

### Unit Tests (Fast, No API Needed)

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/clients/test_reddit_client.py -v

# Run with coverage
pytest tests/unit/ --cov=reddit_flow --cov-report=html

# Run in parallel (faster)
pytest tests/unit/ -n auto
```

### E2E Tests (Mocked APIs)

```bash
pytest tests/e2e/ -v
```

### Integration Tests (Requires API Keys)

```bash
# Run integration tests (skipped if credentials missing)
pytest tests/integration/ -v --run-integration
```

### All Tests

```bash
pytest tests/unit/ tests/e2e/ -v
```

## Code Quality Tools

### Type Checking (mypy)

```bash
# Check entire package
mypy reddit_flow/

# Should show: "Success: no issues found"
```

### Linting (flake8)

```bash
flake8 reddit_flow/ tests/
```

### Formatting (black + isort)

```bash
# Format code
black reddit_flow/ tests/

# Sort imports
isort reddit_flow/ tests/

# Check without changing
black --check reddit_flow/ tests/
isort --check-only reddit_flow/ tests/
```

### Run All Checks

```bash
# Pre-commit runs all checks
pre-commit run --all-files
```

## Project Structure Overview

```
reddit_flow/
├── clients/          # API integrations (Reddit, Gemini, etc.)
├── services/         # Business logic layer
├── models/           # Pydantic data models
├── config/           # Settings and logging
├── exceptions/       # Custom error types
├── utils/            # Retry, validation, logging utilities
└── bot/              # Telegram bot handlers
```

### Key Concepts

1. **Clients** wrap external APIs with consistent interfaces
2. **Services** orchestrate business logic using clients
3. **Models** ensure type-safe data throughout the system
4. **Utils** provide cross-cutting concerns (retry, logging)

## Writing Tests

### Unit Test Example

```python
# tests/unit/clients/test_reddit_client.py
import pytest
from unittest.mock import Mock, patch, MagicMock

from reddit_flow.clients.reddit_client import RedditClient
from reddit_flow.models.reddit import LinkInfo, RedditPost


class TestRedditClient:
    @pytest.fixture
    def mock_settings(self):
        settings = Mock()
        settings.reddit_client_id = "test_id"
        settings.reddit_client_secret = "test_secret"
        return settings

    @pytest.fixture
    def client(self, mock_settings):
        with patch('reddit_flow.clients.reddit_client.praw.Reddit'):
            return RedditClient(mock_settings)

    def test_get_post_data_success(self, client):
        # Arrange
        link_info = LinkInfo(subreddit="Python", post_id="abc123")

        # Act
        result = client.get_post_data(link_info)

        # Assert
        assert isinstance(result, RedditPost)
```

### Async Test Example

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_generate_script():
    mock_client = AsyncMock()
    mock_client.generate_script.return_value = VideoScript(...)

    service = ScriptService(mock_client)
    result = await service.generate(post)

    assert result.title is not None
```

## Common Tasks

### Adding a New Client

1. Create `reddit_flow/clients/new_client.py`
2. Inherit from `BaseClient`
3. Implement required methods
4. Add unit tests in `tests/unit/clients/test_new_client.py`
5. Export from `reddit_flow/clients/__init__.py`

### Adding a New Service

1. Create `reddit_flow/services/new_service.py`
2. Inject client dependencies via constructor
3. Add unit tests with mocked clients
4. Export from `reddit_flow/services/__init__.py`

### Adding a New Model

1. Add Pydantic model to appropriate file in `reddit_flow/models/`
2. Use type hints and validators
3. Add tests in `tests/unit/models/`

## Debugging Tips

### Enable Debug Logging

```bash
# Set in .env
LOG_LEVEL=DEBUG
```

### VS Code Launch Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run Bot",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/main.py",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Run Tests",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": ["tests/unit/", "-v"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Inspect API Responses

```python
# Use structured logger for debugging
from reddit_flow.utils.structured_logger import StructuredLogger

logger = StructuredLogger("debug")
logger.log_event("api_response", response=response.json())
```

## CI/CD

GitHub Actions workflows are in `.github/workflows/`:

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `ci.yml` | Push/PR | Runs tests, linting, type checks |
| `integration-tests.yml` | Monthly/Manual | Full integration tests |
| `dependabot.yml` | Monthly | Dependency updates |

## Troubleshooting

### Import Errors

```bash
# Make sure you're in the virtual environment
.venv\Scripts\activate  # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### Test Discovery Issues

```bash
# Run from project root
cd reddit-flow
pytest tests/unit/ -v
```

### Pre-commit Failures

```bash
# Update hooks
pre-commit autoupdate

# Run manually to see details
pre-commit run --all-files --verbose
```

## Resources

- [Architecture Documentation](ARCHITECTURE.md)
- [Module Dependencies](MODULE_DEPENDENCIES.md)
- [Service Layer Guide](SERVICE_LAYER.md)
- [Exception Handling](EXCEPTION_HANDLING.md)
- [Main README](../README.md)
