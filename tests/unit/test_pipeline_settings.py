"""Unit tests for multi-platform pipeline configuration defaults."""

import os
from pathlib import Path
from unittest.mock import patch

from reddit_flow.config.settings import Settings


def _valid_env_vars(tmp_path: Path) -> dict[str, str]:
    secrets_file = tmp_path / "client_secrets.json"
    secrets_file.write_text('{"installed": {}}')
    return {
        "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
        "REDDIT_CLIENT_ID": "abc123",
        "REDDIT_CLIENT_SECRET": "secret123",
        "REDDIT_USER_AGENT": "TestBot/1.0",
        "REDDIT_USERNAME": "testuser",
        "REDDIT_PASSWORD": "testpass",
        "GOOGLE_API_KEY": "google-api-key-123",
        "ELEVENLABS_API_KEY": "eleven-api-key",
        "ELEVENLABS_VOICE_ID": "voice123",
        "HEYGEN_API_KEY": "heygen-api-key",
        "HEYGEN_AVATAR_ID": "avatar123",
        "YOUTUBE_CLIENT_SECRETS_FILE": str(secrets_file),
    }


class TestPipelineSettingsDefaults:
    """Tests for new feature flags and provider defaults."""

    def test_feature_flags_default_to_safe_values(self, tmp_path: Path):
        """New integrations should be disabled until explicitly enabled."""
        with patch.dict(os.environ, _valid_env_vars(tmp_path), clear=True):
            settings = Settings(_env_file=None)

        assert settings.enable_medium is False
        assert settings.enable_instagram_publish is False
        assert settings.enable_instagram_export is False
        assert settings.enable_whatsapp is False
        assert settings.enable_provider_fallbacks is True

    def test_provider_defaults_and_enabled_lists_are_loaded(self, tmp_path: Path):
        """Provider and source defaults should have predictable values."""
        env_vars = _valid_env_vars(tmp_path)
        env_vars["ENABLED_SOURCES"] = "reddit,medium"
        env_vars["ENABLED_DESTINATIONS"] = "youtube,instagram"
        env_vars["SCRIPT_PROVIDER_FALLBACKS"] = "openai,anthropic"

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings(_env_file=None)

        assert settings.default_script_provider == "gemini"
        assert settings.default_voice_provider == "elevenlabs"
        assert settings.default_video_provider == "heygen"
        assert settings.enabled_sources == ["reddit", "medium"]
        assert settings.enabled_destinations == ["youtube", "instagram"]
        assert settings.script_provider_fallbacks == ["openai", "anthropic"]
