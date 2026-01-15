"""
ElevenLabs TTS API client.

This module provides the client for text-to-speech conversion using
the ElevenLabs API.
"""

import os
from typing import Any, Dict, Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from reddit_flow.clients.base import BaseClient, HTTPClientMixin
from reddit_flow.config import get_logger
from reddit_flow.exceptions import ConfigurationError, TTSError

logger = get_logger(__name__)


class ElevenLabsClient(BaseClient, HTTPClientMixin):
    """
    Client for ElevenLabs text-to-speech API.

    This client handles converting text to speech audio using the
    ElevenLabs API.

    Attributes:
        service_name: Name of the service for logging/identification.
        base_url: The ElevenLabs API base URL.

    Example:
        >>> client = ElevenLabsClient(config={
        ...     "api_key": "your-key",
        ...     "voice_id": "your-voice-id"
        ... })
        >>> audio_bytes = client.text_to_speech("Hello, world!")
    """

    service_name = "ElevenLabs"

    # API configuration
    DEFAULT_BASE_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_TIMEOUT = 60

    def _initialize(self) -> None:
        """
        Initialize the ElevenLabs client.

        Loads API key and voice ID from config or environment variables.

        Raises:
            ConfigurationError: If API key or voice ID is missing.
        """
        # Get API key from config or environment
        self._api_key = self._config.get("api_key") or os.getenv("ELEVENLABS_API_KEY")
        self._voice_id = self._config.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID")

        if not self._api_key:
            raise ConfigurationError(
                "ElevenLabs API key not found",
                details={
                    "required": "ELEVENLABS_API_KEY environment variable or api_key in config"
                },
            )

        if not self._voice_id:
            raise ConfigurationError(
                "ElevenLabs voice ID not found",
                details={
                    "required": "ELEVENLABS_VOICE_ID environment variable or voice_id in config"
                },
            )

        # Get optional settings
        self._base_url = self._config.get("base_url", self.DEFAULT_BASE_URL)
        self._timeout = self._config.get("timeout", self.DEFAULT_TIMEOUT)

        logger.info(
            "ElevenLabs client initialized",
            extra={"voice_id": self._voice_id[:8] + "..."},
        )

    def _health_check(self) -> bool:
        """
        Verify the ElevenLabs API is accessible.

        Checks the user subscription info endpoint to verify credentials.

        Returns:
            True if the API is accessible and credentials are valid.
        """
        try:
            url = f"{self._base_url}/user/subscription"
            headers = self._get_auth_headers()
            response = requests.get(url, headers=headers, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"ElevenLabs health check failed: {e}")
            return False

    @property
    def voice_id(self) -> str:
        """Get the configured voice ID."""
        return self._voice_id  # type: ignore[return-value]

    @property
    def base_url(self) -> str:  # type: ignore[override]
        """Get the API base URL."""
        return self._base_url  # type: ignore[return-value]

    def _get_auth_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Get headers with API key authentication.

        Args:
            extra: Optional additional headers to include.

        Returns:
            Dictionary of headers including API key.
        """
        headers: dict[str, str] = {
            "xi-api-key": str(self._api_key),
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def text_to_speech(self, text: str) -> bytes:
        """
        Convert text to speech audio.

        Args:
            text: Text to convert to speech.

        Returns:
            Audio data as bytes (MP3 format).

        Raises:
            TTSError: If conversion fails.

        Example:
            >>> audio = client.text_to_speech("Hello, world!")
            >>> with open("output.mp3", "wb") as f:
            ...     f.write(audio)
        """
        try:
            url = f"{self._base_url}/text-to-speech/{self._voice_id}"
            headers = self._get_auth_headers()
            data = {"text": text}

            logger.debug(f"Converting {len(text)} characters to speech")
            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()

            audio_size = len(response.content)
            logger.info(f"Generated audio: {audio_size / 1024:.2f} KB")
            return response.content

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            response_text = e.response.text if e.response else str(e)
            logger.error(f"ElevenLabs API error: {status_code} - {response_text}")
            raise TTSError(
                f"Text-to-speech conversion failed: {e}",
                status_code=status_code,
                response_body=response_text,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in text-to-speech: {e}")
            raise TTSError(f"Network error during text-to-speech: {e}")
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}", exc_info=True)
            raise TTSError(f"Failed to convert text to speech: {e}")

    def get_voices(self) -> list:
        """
        Get list of available voices.

        Returns:
            List of voice dictionaries with id, name, and other info.

        Raises:
            TTSError: If API call fails.
        """
        try:
            url = f"{self._base_url}/voices"
            headers = self._get_auth_headers()
            response = requests.get(url, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json().get("voices", [])
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to get voices: {e}")
            raise TTSError(f"Failed to get voices: {e}")
        except Exception as e:
            logger.error(f"Error getting voices: {e}")
            raise TTSError(f"Error getting voices: {e}")

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get user subscription information.

        Returns:
            Dictionary with subscription details including character quota.

        Raises:
            TTSError: If API call fails.
        """
        try:
            url = f"{self._base_url}/user/subscription"
            headers = self._get_auth_headers()
            response = requests.get(url, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to get user info: {e}")
            raise TTSError(f"Failed to get user info: {e}")
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            raise TTSError(f"Error getting user info: {e}")
