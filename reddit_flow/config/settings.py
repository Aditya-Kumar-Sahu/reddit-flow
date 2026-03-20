"""
Application settings and configuration.

This module provides environment-based configuration management using Pydantic.
All settings are loaded from environment variables with validation.

Example usage:
    from reddit_flow.config import Settings

    settings = Settings()
    print(settings.reddit_client_id)

    # Or load from custom .env file
    settings = Settings(_env_file=".env.production")
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from reddit_flow.exceptions import ConfigurationError


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All required fields must be set via environment variables or .env file.
    Optional fields have sensible defaults.

    Attributes:
        env: Environment mode ("test" or "prod"). Default: "prod"
        telegram_bot_token: Telegram bot API token
        reddit_client_id: Reddit API client ID
        reddit_client_secret: Reddit API client secret
        reddit_user_agent: Reddit API user agent string
        reddit_username: Reddit account username
        reddit_password: Reddit account password
        google_api_key: Google/Gemini API key
        elevenlabs_api_key: ElevenLabs API key
        elevenlabs_voice_id: ElevenLabs voice ID
        heygen_api_key: HeyGen API key
        heygen_avatar_id: HeyGen avatar ID
        youtube_client_secrets_file: Path to YouTube OAuth client secrets JSON
        youtube_category_id: YouTube video category ID (default: 28 = Science & Tech)
        youtube_region_code: YouTube region code (default: IN)
        max_comments: Maximum comments to fetch (default: 20)
        script_max_words: Maximum words in generated script (default: 200)
        heygen_wait_timeout: HeyGen video generation timeout in seconds (default: 1800)
        heygen_video_width: Video width in pixels (default: 1080)
        heygen_video_height: Video height in pixels (default: 1920)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars
    )

    # =========================================================================
    # Required Configuration - Must be set via environment
    # =========================================================================

    # Environment settings
    env: Literal["test", "prod"] = "prod"

    # Telegram
    telegram_bot_token: SecretStr = Field(
        ...,
        description="Telegram Bot API token",
    )

    # Reddit
    reddit_client_id: str = Field(
        ...,
        min_length=1,
        description="Reddit API client ID",
    )
    reddit_client_secret: SecretStr = Field(
        ...,
        description="Reddit API client secret",
    )
    reddit_user_agent: str = Field(
        ...,
        min_length=1,
        description="Reddit API user agent string",
    )
    reddit_username: str = Field(
        ...,
        min_length=1,
        description="Reddit account username",
    )
    reddit_password: SecretStr = Field(
        ...,
        description="Reddit account password",
    )

    # Google/Gemini
    google_api_key: SecretStr = Field(
        ...,
        description="Google/Gemini API key",
    )

    # ElevenLabs
    elevenlabs_api_key: SecretStr = Field(
        ...,
        description="ElevenLabs API key for text-to-speech",
    )
    elevenlabs_voice_id: str = Field(
        ...,
        min_length=1,
        description="ElevenLabs voice ID",
    )

    # HeyGen
    heygen_api_key: SecretStr = Field(
        ...,
        description="HeyGen API key for avatar video generation",
    )
    heygen_avatar_id: str = Field(
        ...,
        min_length=1,
        description="HeyGen avatar ID",
    )

    # YouTube
    youtube_client_secrets_file: str = Field(
        ...,
        min_length=1,
        description="Path to YouTube OAuth client secrets JSON file",
    )

    # =========================================================================
    # Optional Configuration - Has sensible defaults
    # =========================================================================

    youtube_category_id: str = Field(
        default="28",
        description="YouTube video category ID (28 = Science & Technology)",
    )
    youtube_region_code: str = Field(
        default="IN",
        min_length=2,
        max_length=2,
        description="YouTube region code (ISO 3166-1 alpha-2)",
    )
    max_comments: int = Field(
        default=20,
        ge=1,
        le=500,
        description="Maximum number of comments to fetch from Reddit",
    )
    script_max_words: int = Field(
        default=200,
        ge=50,
        le=2000,
        description="Maximum words in generated video script",
    )
    heygen_wait_timeout: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="HeyGen video generation timeout in seconds (default: 30 min)",
    )
    heygen_video_width: int = Field(
        default=1080,
        ge=480,
        le=3840,
        description="Video width in pixels",
    )
    heygen_video_height: int = Field(
        default=1920,
        ge=480,
        le=3840,
        description="Video height in pixels",
    )

    # =========================================================================
    # Optional paths
    # =========================================================================

    temp_dir: str = Field(
        default="temp",
        description="Directory for temporary files",
    )
    logs_dir: str = Field(
        default="logs",
        description="Directory for log files",
    )

    # =========================================================================
    # Multi-platform pipeline settings
    # =========================================================================

    enable_medium: bool = Field(
        default=False,
        description="Enable Medium ingestion adapters",
    )
    enable_instagram_publish: bool = Field(
        default=False,
        description="Enable direct Instagram publishing",
    )
    enable_instagram_export: bool = Field(
        default=False,
        description="Enable Instagram export bundle generation",
    )
    enable_whatsapp: bool = Field(
        default=False,
        description="Enable WhatsApp messaging channel",
    )
    enable_provider_fallbacks: bool = Field(
        default=True,
        description="Enable fallback provider resolution",
    )

    enabled_sources: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["reddit"],
        description="Enabled canonical source adapters",
    )
    enabled_destinations: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["youtube"],
        description="Enabled publish destinations",
    )
    default_script_provider: str = Field(
        default="gemini",
        description="Default script provider name",
    )
    default_voice_provider: str = Field(
        default="elevenlabs",
        description="Default voice provider name",
    )
    default_video_provider: str = Field(
        default="heygen",
        description="Default video provider name",
    )
    script_provider_fallbacks: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Fallback script providers in resolution order",
    )
    voice_provider_fallbacks: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Fallback voice providers in resolution order",
    )
    video_provider_fallbacks: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Fallback video providers in resolution order",
    )

    medium_user_agent: str = Field(
        default="reddit-flow/0.1",
        description="User agent used for Medium content retrieval",
    )
    medium_request_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout for Medium feed/article requests in seconds",
    )

    meta_app_id: str | None = Field(
        default=None,
        description="Meta app ID for Instagram/WhatsApp integrations",
    )
    meta_app_secret: SecretStr | None = Field(
        default=None,
        description="Meta app secret",
    )
    instagram_access_token: SecretStr | None = Field(
        default=None,
        description="Instagram Graph API access token",
    )
    instagram_business_account_id: str | None = Field(
        default=None,
        description="Instagram business account ID",
    )
    whatsapp_access_token: SecretStr | None = Field(
        default=None,
        description="WhatsApp Cloud API access token",
    )
    whatsapp_phone_number_id: str | None = Field(
        default=None,
        description="WhatsApp phone number ID",
    )
    whatsapp_verify_token: SecretStr | None = Field(
        default=None,
        description="WhatsApp webhook verification token",
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("youtube_client_secrets_file")
    @classmethod
    def validate_youtube_secrets_file(cls, v: str, info: ValidationInfo) -> str:
        """Validate YouTube client secrets file exists (only in prod mode)."""
        # Skip file existence check in test mode
        if info.data.get("env") == "test":
            return v
        path = Path(v)
        if not path.exists():
            raise ValueError(
                f"YouTube client secrets file not found: {v}. "
                "Please download it from Google Cloud Console."
            )
        if not path.suffix == ".json":
            raise ValueError(f"YouTube client secrets file must be JSON: {v}")
        return v

    @field_validator("youtube_region_code")
    @classmethod
    def validate_region_code(cls, v: str) -> str:
        """Validate region code is uppercase."""
        return v.upper()

    @field_validator(
        "default_script_provider",
        "default_voice_provider",
        "default_video_provider",
        mode="before",
    )
    @classmethod
    def normalize_provider_name(cls, v: str) -> str:
        """Normalize provider names for registry lookups."""
        return str(v).strip().lower()

    @field_validator(
        "enabled_sources",
        "enabled_destinations",
        "script_provider_fallbacks",
        "voice_provider_fallbacks",
        "video_provider_fallbacks",
        mode="before",
    )
    @classmethod
    def parse_csv_list(cls, v: str | list[str] | None) -> list[str]:
        """Allow list-based settings to be provided as CSV strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        return [str(item).strip().lower() for item in v if str(item).strip()]

    @model_validator(mode="after")
    def validate_video_dimensions(self) -> "Settings":
        """Validate video dimensions are reasonable."""
        if self.heygen_video_width > self.heygen_video_height:
            # Landscape video - warn but allow
            pass
        return self

    # =========================================================================
    # Computed Properties
    # =========================================================================

    @property
    def video_aspect_ratio(self) -> str:
        """Get video aspect ratio as string."""
        from math import gcd

        divisor = gcd(self.heygen_video_width, self.heygen_video_height)
        w = self.heygen_video_width // divisor
        h = self.heygen_video_height // divisor
        return f"{w}:{h}"

    @property
    def is_portrait_video(self) -> bool:
        """Check if video is in portrait orientation."""
        return self.heygen_video_height > self.heygen_video_width

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_reddit_secret(self) -> str:
        """Get Reddit client secret as plain string."""
        return self.reddit_client_secret.get_secret_value()

    def get_reddit_password(self) -> str:
        """Get Reddit password as plain string."""
        return self.reddit_password.get_secret_value()

    def get_google_api_key(self) -> str:
        """Get Google API key as plain string."""
        return self.google_api_key.get_secret_value()

    def get_elevenlabs_api_key(self) -> str:
        """Get ElevenLabs API key as plain string."""
        return self.elevenlabs_api_key.get_secret_value()

    def get_heygen_api_key(self) -> str:
        """Get HeyGen API key as plain string."""
        return self.heygen_api_key.get_secret_value()

    def get_telegram_token(self) -> str:
        """Get Telegram bot token as plain string."""
        return self.telegram_bot_token.get_secret_value()

    def ensure_directories(self) -> None:
        """Ensure temp and logs directories exist."""
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        Path(self.logs_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses LRU cache to ensure settings are only loaded once.

    Returns:
        Settings instance loaded from environment.

    Raises:
        ConfigurationError: If required settings are missing.
    """
    try:
        return Settings()
    except Exception as e:
        raise ConfigurationError(
            f"Failed to load configuration: {e}\n"
            "Please check your .env file. See .env.example for reference."
        ) from e


def validate_settings() -> Settings:
    """
    Validate and return settings, clearing cache first.

    Use this for explicit validation on startup.

    Returns:
        Validated Settings instance.

    Raises:
        ConfigurationError: If validation fails.
    """
    get_settings.cache_clear()
    return get_settings()
