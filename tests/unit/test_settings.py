"""
Unit tests for Settings configuration module.

Tests cover:
- Settings initialization with environment variables
- Required field validation
- Optional field defaults
- Field validators
- Computed properties
- Helper methods
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from reddit_flow.config.settings import Settings, get_settings, validate_settings
from reddit_flow.exceptions import ConfigurationError

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_env_vars(tmp_path: Path) -> dict[str, str]:
    """Create a complete set of valid environment variables."""
    # Create a dummy YouTube secrets file
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


@pytest.fixture
def settings_with_env(valid_env_vars: dict[str, str]):
    """Create settings with environment variables patched."""
    with patch.dict(os.environ, valid_env_vars, clear=True):
        # Clear the cache before creating new settings
        get_settings.cache_clear()
        yield Settings(_env_file=None)


# =============================================================================
# Settings Initialization Tests
# =============================================================================


class TestSettingsInitialization:
    """Tests for Settings class initialization."""

    def test_settings_with_all_required_vars(self, valid_env_vars: dict[str, str]):
        """Test settings loads successfully with all required vars."""
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.reddit_client_id == "abc123"
            assert settings.reddit_user_agent == "TestBot/1.0"

    def test_settings_missing_required_var(self, valid_env_vars: dict[str, str]):
        """Test settings fails with missing required var."""
        del valid_env_vars["REDDIT_CLIENT_ID"]
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "reddit_client_id" in str(exc_info.value)

    def test_settings_missing_multiple_required_vars(self, tmp_path: Path):
        """Test settings reports all missing required vars."""
        secrets_file = tmp_path / "client_secrets.json"
        secrets_file.write_text("{}")

        with patch.dict(
            os.environ,
            {
                "YOUTUBE_CLIENT_SECRETS_FILE": str(secrets_file),
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            # Should have multiple validation errors
            assert "telegram_bot_token" in str(exc_info.value).lower()

    def test_settings_empty_required_var(self, valid_env_vars: dict[str, str]):
        """Test settings fails with empty required var."""
        valid_env_vars["REDDIT_CLIENT_ID"] = ""
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)


# =============================================================================
# Secret Fields Tests
# =============================================================================


class TestSecretFields:
    """Tests for SecretStr fields."""

    def test_secret_fields_are_masked(self, settings_with_env: Settings):
        """Test that secret fields are masked in string representation."""
        settings_str = str(settings_with_env)
        assert "secret123" not in settings_str
        assert "testpass" not in settings_str

    def test_get_reddit_secret(self, settings_with_env: Settings):
        """Test getting Reddit secret as plain string."""
        assert settings_with_env.get_reddit_secret() == "secret123"

    def test_get_reddit_password(self, settings_with_env: Settings):
        """Test getting Reddit password as plain string."""
        assert settings_with_env.get_reddit_password() == "testpass"

    def test_get_google_api_key(self, settings_with_env: Settings):
        """Test getting Google API key as plain string."""
        assert settings_with_env.get_google_api_key() == "google-api-key-123"

    def test_get_elevenlabs_api_key(self, settings_with_env: Settings):
        """Test getting ElevenLabs API key as plain string."""
        assert settings_with_env.get_elevenlabs_api_key() == "eleven-api-key"

    def test_get_heygen_api_key(self, settings_with_env: Settings):
        """Test getting HeyGen API key as plain string."""
        assert settings_with_env.get_heygen_api_key() == "heygen-api-key"

    def test_get_telegram_token(self, settings_with_env: Settings):
        """Test getting Telegram token as plain string."""
        token = settings_with_env.get_telegram_token()
        assert token == "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"


# =============================================================================
# Default Values Tests
# =============================================================================


class TestDefaultValues:
    """Tests for optional field default values."""

    def test_youtube_category_id_default(self, settings_with_env: Settings):
        """Test default YouTube category ID."""
        assert settings_with_env.youtube_category_id == "28"

    def test_youtube_region_code_default(self, settings_with_env: Settings):
        """Test default YouTube region code."""
        assert settings_with_env.youtube_region_code == "IN"

    def test_max_comments_default(self, settings_with_env: Settings):
        """Test default max comments."""
        assert settings_with_env.max_comments == 20

    def test_script_max_words_default(self, settings_with_env: Settings):
        """Test default script max words."""
        assert settings_with_env.script_max_words == 200

    def test_heygen_wait_timeout_default(self, settings_with_env: Settings):
        """Test default HeyGen wait timeout."""
        assert settings_with_env.heygen_wait_timeout == 1800

    def test_heygen_video_dimensions_default(self, settings_with_env: Settings):
        """Test default video dimensions."""
        assert settings_with_env.heygen_video_width == 1080
        assert settings_with_env.heygen_video_height == 1920

    def test_temp_dir_default(self, settings_with_env: Settings):
        """Test default temp directory."""
        assert settings_with_env.temp_dir == "temp"

    def test_logs_dir_default(self, settings_with_env: Settings):
        """Test default logs directory."""
        assert settings_with_env.logs_dir == "logs"


class TestOptionalOverrides:
    """Tests for overriding optional field defaults."""

    def test_override_max_comments(self, valid_env_vars: dict[str, str]):
        """Test overriding max comments."""
        valid_env_vars["MAX_COMMENTS"] = "50"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.max_comments == 50

    def test_override_script_max_words(self, valid_env_vars: dict[str, str]):
        """Test overriding script max words."""
        valid_env_vars["SCRIPT_MAX_WORDS"] = "500"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.script_max_words == 500

    def test_override_video_dimensions(self, valid_env_vars: dict[str, str]):
        """Test overriding video dimensions."""
        valid_env_vars["HEYGEN_VIDEO_WIDTH"] = "1920"
        valid_env_vars["HEYGEN_VIDEO_HEIGHT"] = "1080"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.heygen_video_width == 1920
            assert settings.heygen_video_height == 1080


# =============================================================================
# Field Validation Tests
# =============================================================================


class TestFieldValidation:
    """Tests for field validators."""

    def test_youtube_secrets_file_not_found(self, valid_env_vars: dict[str, str]):
        """Test validation fails for non-existent secrets file."""
        valid_env_vars["YOUTUBE_CLIENT_SECRETS_FILE"] = "/nonexistent/path.json"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "not found" in str(exc_info.value)

    def test_youtube_secrets_file_wrong_extension(
        self, valid_env_vars: dict[str, str], tmp_path: Path
    ):
        """Test validation fails for non-JSON secrets file."""
        wrong_file = tmp_path / "secrets.txt"
        wrong_file.write_text("not json")
        valid_env_vars["YOUTUBE_CLIENT_SECRETS_FILE"] = str(wrong_file)
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "must be JSON" in str(exc_info.value)

    def test_region_code_uppercase(self, valid_env_vars: dict[str, str]):
        """Test region code is converted to uppercase."""
        valid_env_vars["YOUTUBE_REGION_CODE"] = "us"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.youtube_region_code == "US"

    def test_max_comments_minimum(self, valid_env_vars: dict[str, str]):
        """Test max comments minimum validation."""
        valid_env_vars["MAX_COMMENTS"] = "0"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "max_comments" in str(exc_info.value).lower()

    def test_max_comments_maximum(self, valid_env_vars: dict[str, str]):
        """Test max comments maximum validation."""
        valid_env_vars["MAX_COMMENTS"] = "1000"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "max_comments" in str(exc_info.value).lower()

    def test_script_max_words_minimum(self, valid_env_vars: dict[str, str]):
        """Test script max words minimum validation."""
        valid_env_vars["SCRIPT_MAX_WORDS"] = "10"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "script_max_words" in str(exc_info.value).lower()

    def test_heygen_timeout_minimum(self, valid_env_vars: dict[str, str]):
        """Test HeyGen timeout minimum validation."""
        valid_env_vars["HEYGEN_WAIT_TIMEOUT"] = "30"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            assert "heygen_wait_timeout" in str(exc_info.value).lower()


# =============================================================================
# Computed Properties Tests
# =============================================================================


class TestComputedProperties:
    """Tests for computed properties."""

    def test_video_aspect_ratio_portrait(self, settings_with_env: Settings):
        """Test aspect ratio for portrait video."""
        # Default is 1080x1920 = 9:16
        assert settings_with_env.video_aspect_ratio == "9:16"

    def test_video_aspect_ratio_landscape(self, valid_env_vars: dict[str, str]):
        """Test aspect ratio for landscape video."""
        valid_env_vars["HEYGEN_VIDEO_WIDTH"] = "1920"
        valid_env_vars["HEYGEN_VIDEO_HEIGHT"] = "1080"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.video_aspect_ratio == "16:9"

    def test_is_portrait_video_true(self, settings_with_env: Settings):
        """Test portrait video detection."""
        assert settings_with_env.is_portrait_video is True

    def test_is_portrait_video_false(self, valid_env_vars: dict[str, str]):
        """Test landscape video detection."""
        valid_env_vars["HEYGEN_VIDEO_WIDTH"] = "1920"
        valid_env_vars["HEYGEN_VIDEO_HEIGHT"] = "1080"
        with patch.dict(os.environ, valid_env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.is_portrait_video is False


# =============================================================================
# Helper Methods Tests
# =============================================================================


class TestHelperMethods:
    """Tests for helper methods."""

    def test_ensure_directories(self, settings_with_env: Settings, tmp_path: Path):
        """Test ensure_directories creates directories."""
        # Temporarily override directories
        settings_with_env.temp_dir = str(tmp_path / "test_temp")
        settings_with_env.logs_dir = str(tmp_path / "test_logs")

        settings_with_env.ensure_directories()

        assert (tmp_path / "test_temp").exists()
        assert (tmp_path / "test_logs").exists()


# =============================================================================
# get_settings Function Tests
# =============================================================================


class TestGetSettings:
    """Tests for get_settings cached function."""

    def test_get_settings_caches_result(self, valid_env_vars: dict[str, str]):
        """Test that get_settings caches the result."""
        with patch.dict(os.environ, valid_env_vars, clear=True):
            get_settings.cache_clear()
            # Patch Settings to not load .env file
            with patch("reddit_flow.config.settings.Settings"):
                settings1 = get_settings()
                settings2 = get_settings()
                assert settings1 is settings2

    def test_get_settings_raises_configuration_error(self):
        """Test that get_settings wraps errors in ConfigurationError."""
        get_settings.cache_clear()
        # Patch Settings to raise an exception
        with patch("reddit_flow.config.settings.Settings") as MockSettings:
            MockSettings.side_effect = ValueError("Missing required field")
            with pytest.raises(ConfigurationError) as exc_info:
                get_settings()
            assert "Failed to load configuration" in str(exc_info.value)


# =============================================================================
# validate_settings Function Tests
# =============================================================================


class TestValidateSettings:
    """Tests for validate_settings function."""

    def test_validate_settings_clears_cache(self):
        """Test that validate_settings clears cache."""
        get_settings.cache_clear()
        with patch("reddit_flow.config.settings.Settings") as MockSettings:
            settings1 = get_settings()

            # Now call validate_settings which should clear cache
            mock_instance_2 = object()
            MockSettings.return_value = mock_instance_2
            settings2 = validate_settings()
            # After cache clear, should be new instance
            assert settings1 is not settings2

    def test_validate_settings_returns_valid_settings(self, valid_env_vars: dict[str, str]):
        """Test validate_settings returns settings on success."""
        with patch.dict(os.environ, valid_env_vars, clear=True):
            get_settings.cache_clear()
            with patch("reddit_flow.config.settings.Settings") as MockSettings:
                mock_settings = MockSettings.return_value
                mock_settings.reddit_client_id = "abc123"
                settings = validate_settings()
                assert settings.reddit_client_id == "abc123"


# =============================================================================
# Case Sensitivity Tests
# =============================================================================


class TestCaseSensitivity:
    """Tests for case-insensitive environment variable handling."""

    def test_lowercase_env_vars_work(self, valid_env_vars: dict[str, str], tmp_path: Path):
        """Test that lowercase env vars are accepted."""
        secrets_file = tmp_path / "client_secrets.json"
        secrets_file.write_text("{}")

        lowercase_vars = {k.lower(): v for k, v in valid_env_vars.items()}
        lowercase_vars["youtube_client_secrets_file"] = str(secrets_file)

        with patch.dict(os.environ, lowercase_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.reddit_client_id == "abc123"
