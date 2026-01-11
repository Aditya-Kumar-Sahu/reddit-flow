import asyncio
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai
import praw
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Google API imports for YouTube
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
logger = logging.getLogger(__name__)


# --- Custom Exceptions ---
class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""

    pass


class RedditAPIError(Exception):
    """Raised when Reddit API operations fail."""

    pass


class AIGenerationError(Exception):
    """Raised when AI content generation fails."""

    pass


class TTSError(Exception):
    """Raised when text-to-speech conversion fails."""

    pass


class VideoGenerationError(Exception):
    """Raised when avatar video generation fails."""

    pass


class YouTubeUploadError(Exception):
    """Raised when YouTube upload fails."""

    pass


# --- Configuration ---
class Config:
    """Application configuration with validation."""

    # Required configuration
    TELEGRAM_BOT_TOKEN: str
    REDDIT_CLIENT_ID: str
    REDDIT_CLIENT_SECRET: str
    REDDIT_USER_AGENT: str
    REDDIT_USERNAME: str
    REDDIT_PASSWORD: str
    GOOGLE_API_KEY: str
    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str
    HEYGEN_API_KEY: str
    HEYGEN_AVATAR_ID: str
    YOUTUBE_CLIENT_SECRETS_FILE: str

    # Optional configuration with defaults
    YOUTUBE_CATEGORY_ID: str = "28"
    YOUTUBE_REGION_CODE: str = "IN"
    MAX_COMMENTS: int = 20
    SCRIPT_MAX_WORDS: int = 200
    HEYGEN_WAIT_TIMEOUT: int = 1800  # 30 minutes
    HEYGEN_VIDEO_WIDTH: int = 1080  # 9:16 aspect ratio
    HEYGEN_VIDEO_HEIGHT: int = 1920

    # Constants
    REDDIT_URL_PATTERN = re.compile(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)")

    @classmethod
    def validate_and_load(cls) -> None:
        """Validate all required environment variables are set."""
        required_vars = [
            "TELEGRAM_BOT_TOKEN",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "REDDIT_USER_AGENT",
            "REDDIT_USERNAME",
            "REDDIT_PASSWORD",
            "GOOGLE_API_KEY",
            "ELEVENLABS_API_KEY",
            "ELEVENLABS_VOICE_ID",
            "HEYGEN_API_KEY",
            "HEYGEN_AVATAR_ID",
            "YOUTUBE_CLIENT_SECRETS_FILE",
        ]

        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                setattr(cls, var, value)

        if missing_vars:
            raise ConfigurationError(
                "Missing required environment variables: {}\n"
                "Please check your .env file. See .env.example for reference.".format(
                    ", ".join(missing_vars)
                )
            )

        # Load optional configuration
        cls.YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", cls.YOUTUBE_CATEGORY_ID)
        cls.YOUTUBE_REGION_CODE = os.getenv("YOUTUBE_REGION_CODE", cls.YOUTUBE_REGION_CODE)
        cls.MAX_COMMENTS = int(os.getenv("MAX_COMMENTS", cls.MAX_COMMENTS))
        cls.SCRIPT_MAX_WORDS = int(os.getenv("SCRIPT_MAX_WORDS", cls.SCRIPT_MAX_WORDS))
        cls.HEYGEN_WAIT_TIMEOUT = int(os.getenv("HEYGEN_WAIT_TIMEOUT", cls.HEYGEN_WAIT_TIMEOUT))
        cls.HEYGEN_VIDEO_WIDTH = int(os.getenv("HEYGEN_VIDEO_WIDTH", cls.HEYGEN_VIDEO_WIDTH))
        cls.HEYGEN_VIDEO_HEIGHT = int(os.getenv("HEYGEN_VIDEO_HEIGHT", cls.HEYGEN_VIDEO_HEIGHT))

        logger.info("Configuration validated successfully")


# --- Service Classes ---


class RedditClient:
    """Client for interacting with Reddit API."""

    def __init__(self):
        try:
            self.reddit = praw.Reddit(
                client_id=Config.REDDIT_CLIENT_ID,
                client_secret=Config.REDDIT_CLIENT_SECRET,
                user_agent=Config.REDDIT_USER_AGENT,
                username=Config.REDDIT_USERNAME,
                password=Config.REDDIT_PASSWORD,
            )
            logger.info("Reddit client initialized")
        except Exception as e:
            logger.error("Failed to initialize Reddit client: {}".format(e))
            raise RedditAPIError("Reddit initialization failed: {}".format(e))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (requests.exceptions.RequestException, praw.exceptions.PRAWException)
        ),
    )
    def get_post_data(self, subreddit_name: str, post_id: str) -> Dict[str, Any]:
        """
        Fetch Reddit post data including comments.

        Args:
            subreddit_name: Name of the subreddit
            post_id: Reddit post ID

        Returns:
            Dictionary containing post data and comments

        Raises:
            RedditAPIError: If fetching post data fails
        """
        try:
            logger.info("Fetching post r/{}/{}".format(subreddit_name, post_id))
            submission = self.reddit.submission(id=post_id)

            # Load some comment replies (limited to avoid excessive loading)
            submission.comments.replace_more(limit=5)

            post_data = {
                "title": submission.title,
                "selftext": submission.selftext or "",
                "url": submission.url,
                "author": str(submission.author) if submission.author else "[deleted]",
                "score": submission.score,
                "comments": self._extract_comments(
                    submission.comments.list()[:50]
                ),  # Limit initial comments
            }

            logger.info("Fetched post with {} comments".format(len(post_data["comments"])))
            return post_data

        except praw.exceptions.InvalidURL:
            raise RedditAPIError(
                "Invalid Reddit post: r/{}/comments/{}".format(subreddit_name, post_id)
            )
        except praw.exceptions.NotFound:
            raise RedditAPIError("Post not found: r/{}/comments/{}".format(subreddit_name, post_id))
        except Exception as e:
            logger.error("Error fetching Reddit post: {}".format(e), exc_info=True)
            raise RedditAPIError("Failed to fetch Reddit post: {}".format(e))

    def _extract_comments(self, comments: List, depth: int = 0, max_depth: int = 5) -> List[Dict]:
        """
        Extract comment data recursively with depth limiting.

        Args:
            comments: List of PRAW comment objects
            depth: Current recursion depth
            max_depth: Maximum depth to recurse

        Returns:
            List of comment dictionaries
        """
        all_content = []

        if depth > max_depth:
            return all_content

        for comment in comments:
            if isinstance(comment, praw.models.MoreComments):
                continue

            try:
                content = {
                    "id": comment.id,
                    "body": comment.body,
                    "author": str(comment.author) if comment.author else "[deleted]",
                    "depth": depth,
                    "score": comment.score,
                }

                all_content.append(content)

                # Recursively extract replies
                if hasattr(comment, "replies") and len(comment.replies) > 0:
                    reply_list = comment.replies.list()[:10]  # Limit replies per comment
                    all_content.extend(self._extract_comments(reply_list, depth + 1, max_depth))

            except Exception as e:
                logger.warning(
                    "Error extracting comment {}: {}".format(getattr(comment, "id", "unknown"), e)
                )
                continue

        return all_content


class GeminiClient:
    """Client for Google Gemini AI operations."""

    def __init__(self):
        try:
            genai.configure(api_key=Config.GOOGLE_API_KEY)
            self.model = genai.GenerativeModel("gemini-2.5-flash-lite")
            logger.info("Gemini client initialized")
        except Exception as e:
            logger.error("Failed to initialize Gemini client: {}".format(e))
            raise AIGenerationError("Gemini initialization failed: {}".format(e))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def extract_link_info(self, message_text: str) -> Dict[str, str]:
        """
        Extract Reddit link information from user message.

        Args:
            message_text: Raw message text from user

        Returns:
            Dictionary with link, subReddit, postId, and optional text

        Raises:
            AIGenerationError: If extraction fails
        """
        try:
            prompt = """
            Extract the Reddit link, subreddit, post ID,
            and any additional user text from this message:
            "{}"

            Return JSON with keys: link, subReddit, postId, text.
            If no additional text is provided, set 'text' to null.
            Example JSON format:
            {{
                "link": "https://www.reddit.com/r/sheffield/comments/1nf7kh6/new_ai/",
                "subReddit": "sheffield",
                "postId": "1nf7kh6",
                "text": "text provided by the user other than the link, this can be null"
            }}
            """.format(
                message_text
            )

            logger.debug("Extracting link info with Gemini")
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()

            # Clean up markdown code blocks if present
            text = self._clean_json_response(text)

            result = json.loads(text)

            # Validate required fields
            if not all(key in result for key in ["link", "subReddit", "postId"]):
                raise ValueError("Missing required fields in AI response")

            logger.info(
                "Extracted link info for r/{}/{}".format(result["subReddit"], result["postId"])
            )
            return result

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini JSON response: {}".format(text))
            raise AIGenerationError("Invalid JSON from AI: {}".format(e))
        except Exception as e:
            logger.error("Error extracting link info: {}".format(e), exc_info=True)
            raise AIGenerationError("Failed to extract link information: {}".format(e))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def generate_script(
        self, post_text: str, comments_data: List[Dict], user_opinion: Optional[str]
    ) -> Dict[str, str]:
        """
        Generate video script from Reddit content.

        Args:
            post_text: Main post text
            comments_data: List of comment dictionaries
            user_opinion: Optional user's opinion/context

        Returns:
            Dictionary with 'script' and 'title' keys

        Raises:
            AIGenerationError: If script generation fails
        """
        try:
            # Limit comments to avoid token limits
            limited_comments = comments_data[: Config.MAX_COMMENTS]
            comments_str = json.dumps(limited_comments, indent=2)

            system_prompt = """
            You are an expert script writer for social media content.

            ## Writing Instructions:
            Write a script for a short-form video for a broad audience.
            Do not use emojis in the script, and avoid Gen Z slang.
            The script should be less than {} words with an engaging hook and interactive CTA.

            Write like a confident, clear-thinking human speaking to another smart human.
            Avoid robotic phrases like 'in today's fast-paced world', 'leveraging synergies',
            or 'furthermore'.
            Skip unnecessary dashes (—), quotation marks (""),
            and corporate buzzwords like 'cutting-edge', 'robust', or 'seamless experience'.

            No AI tone. No fluff. No filler.
            Use natural transitions like 'here's the thing', 'let's break it down', or
            'what this really means is…'
            Keep sentences varied in length and rhythm, like how real people speak or write.
            Prioritize clarity, personality, and usefulness.
            Every sentence should feel intentional, not generated.
            Do not ask questions and then answer them yourself.
            Do not describe scenes, just write the speaking script without any markdown.
            """.format(
                Config.SCRIPT_MAX_WORDS
            )

            user_prompt = """
            Post Content: {}

            Comments: {}

            User Opinion: {}

            Generate a video script and title based on this Reddit content.
            Return JSON with keys: 'script' and 'title'.
            """.format(
                post_text, comments_str, user_opinion or "None provided"
            )

            full_prompt = "{}\n\n{}".format(system_prompt, user_prompt)

            logger.debug("Generating script with Gemini")
            response = await self.model.generate_content_async(full_prompt)
            text = response.text.strip()

            text = self._clean_json_response(text)
            result = json.loads(text)

            # Validate response structure
            if "script" not in result or "title" not in result:
                raise ValueError("Missing script or title in AI response")

            # Validate script length
            word_count = len(result["script"].split())
            if word_count > Config.SCRIPT_MAX_WORDS * 1.2:  # Allow 20% overflow
                logger.warning("Script length ({} words) exceeds limit".format(word_count))

            logger.info(
                "Generated script: {} words, title: {}...".format(word_count, result["title"][:50])
            )
            return result

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini JSON response: {}".format(text))
            raise AIGenerationError("Invalid JSON from AI: {}".format(e))
        except Exception as e:
            logger.error("Error generating script: {}".format(e), exc_info=True)
            raise AIGenerationError("Failed to generate script: {}".format(e))

    @staticmethod
    def _clean_json_response(text: str) -> str:
        """Remove markdown code blocks from JSON response."""
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
        return text.strip()


class ElevenLabsClient:
    """Client for ElevenLabs text-to-speech."""

    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        logger.info("ElevenLabs client initialized")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
    )
    def text_to_speech(self, text: str) -> bytes:
        """
        Convert text to speech audio.

        Args:
            text: Text to convert to speech

        Returns:
            Audio data as bytes

        Raises:
            TTSError: If conversion fails
        """
        try:
            url = "{}/text-to-speech/{}".format(self.base_url, self.voice_id)
            headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
            data = {"text": text}

            logger.debug("Converting {} characters to speech".format(len(text)))
            response = requests.post(url, json=data, headers=headers, timeout=60)
            response.raise_for_status()

            audio_size = len(response.content)
            logger.info("Generated audio: {:.2f} KB".format(audio_size / 1024))
            return response.content

        except requests.exceptions.HTTPError as e:
            logger.error(
                "ElevenLabs API error: {} - {}".format(e.response.status_code, e.response.text)
            )
            raise TTSError("Text-to-speech conversion failed: {}".format(e))
        except Exception as e:
            logger.error("Error in text-to-speech: {}".format(e), exc_info=True)
            raise TTSError("Failed to convert text to speech: {}".format(e))


class HeyGenClient:
    """Client for HeyGen avatar video generation (API v2)."""

    def __init__(self):
        self.api_key = Config.HEYGEN_API_KEY
        self.avatar_id = Config.HEYGEN_AVATAR_ID
        self.base_url = "https://api.heygen.com"
        # The upload endpoint is distinct from the main API
        self.upload_url = "https://upload.heygen.com/v1/asset"
        logger.info("HeyGen client initialized")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
    )
    def upload_audio(self, audio_data: bytes) -> str:
        """
        Upload audio to HeyGen (v1/asset).

        Args:
            audio_data: Audio file bytes (MP3/WAV)

        Returns:
            URL of uploaded audio asset

        Raises:
            VideoGenerationError: If upload fails
        """
        try:
            # Content-Type should match the audio format, usually audio/mpeg for mp3
            headers = {"X-API-KEY": self.api_key, "Content-Type": "audio/mpeg"}

            logger.debug("Uploading {:.2f} KB audio to HeyGen".format(len(audio_data) / 1024))

            # Note: The v2 API still uses v1 assets
            response = requests.post(self.upload_url, data=audio_data, headers=headers, timeout=120)
            response.raise_for_status()

            result = response.json()
            # The v1/asset endpoint returns data.url and data.id
            audio_url = result["data"]["url"]
            logger.info("Audio uploaded successfully: {}".format(audio_url))
            return audio_url

        except requests.exceptions.HTTPError as e:
            logger.error(
                "HeyGen upload error: {} - {}".format(e.response.status_code, e.response.text)
            )
            raise VideoGenerationError("Audio upload failed: {}".format(e))
        except Exception as e:
            logger.error("Error uploading audio: {}".format(e), exc_info=True)
            raise VideoGenerationError("Failed to upload audio: {}".format(e))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
    )
    def generate_video(self, audio_url: str, title: str = None) -> str:
        """
        Start avatar video generation using HeyGen API v2.

        Args:
            audio_url: URL of uploaded audio (from upload_audio)
            title: Optional title for the video

        Returns:
            Video ID for tracking generation

        Raises:
            VideoGenerationError: If video generation request fails
        """
        try:
            url = "{}/v2/video/generate".format(self.base_url)
            headers = {"x-api-key": self.api_key, "content-type": "application/json"}

            # V2 Payload Structure:
            # video_inputs is an array of scenes. We use a single scene here.
            data = {
                "video_inputs": [
                    {
                        "character": {
                            "type": "avatar",
                            "avatar_id": self.avatar_id,
                            "avatar_style": "normal",
                        },
                        "voice": {
                            "type": "audio",
                            "audio_url": audio_url,
                            # Alternatively, use "audio_asset_id" if you have the ID
                        },
                        # Background is optional; defaults to transparent/original if omitted
                    }
                ],
                "test": False,  # Set to True for testing (watermarked, no credit usage)
                "caption": True,  # Set to True to generate captions
                "dimension": {
                    "width": Config.HEYGEN_VIDEO_WIDTH,
                    "height": Config.HEYGEN_VIDEO_HEIGHT,
                },
            }

            if title:
                data["title"] = title

            logger.debug("Requesting HeyGen video generation (v2)")
            response = requests.post(url, json=data, headers=headers, timeout=60)
            response.raise_for_status()

            # V2 response structure: data -> video_id
            video_id = response.json()["data"]["video_id"]
            logger.info("Video generation started: {}".format(video_id))
            return video_id

        except requests.exceptions.HTTPError as e:
            logger.error(
                "HeyGen generation error: {} - {}".format(e.response.status_code, e.response.text)
            )
            raise VideoGenerationError("Video generation failed: {}".format(e))
        except Exception as e:
            logger.error("Error generating video: {}".format(e), exc_info=True)
            raise VideoGenerationError("Failed to start video generation: {}".format(e))

    async def wait_for_video(self, video_id: str, update_callback=None) -> str:
        """
        Wait for video generation to complete with timeout (Async).

        Args:
            video_id: HeyGen video ID
            update_callback: Optional async callback for status updates

        Returns:
            URL of completed video
        """
        # Status check is still v1/video_status.get even for v2 videos
        url = "{}/v1/video_status.get".format(self.base_url)
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}

        start_time = time.time()
        attempt = 0
        wait_time = 10
        max_wait_time = 60

        try:
            while True:
                elapsed = time.time() - start_time

                if elapsed > Config.HEYGEN_WAIT_TIMEOUT:
                    raise VideoGenerationError(
                        "Video generation timed out after {} seconds".format(
                            Config.HEYGEN_WAIT_TIMEOUT
                        )
                    )

                attempt += 1
                logger.debug(
                    "Checking video status (attempt {}, elapsed: {:.0f}s)".format(attempt, elapsed)
                )

                # Run blocking request in a thread to avoid blocking the async event loop
                response = await asyncio.to_thread(
                    requests.get, url, params={"video_id": video_id}, headers=headers, timeout=30
                )
                response.raise_for_status()

                data = response.json()["data"]
                status = data["status"]

                if status == "completed":
                    video_url = data["video_url"]
                    logger.info("Video completed after {:.0f}s: {}".format(elapsed, video_url))
                    return video_url

                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    logger.error("HeyGen video generation failed: {}".format(error))
                    raise VideoGenerationError("Video generation failed: {}".format(error))

                if update_callback:
                    await update_callback(
                        "Video generation: {} ({:.0f}s elapsed)".format(status, elapsed)
                    )

                logger.info("Video status: {}, waiting {}s...".format(status, wait_time))
                await asyncio.sleep(wait_time)

                wait_time = min(wait_time * 1.5, max_wait_time)

        except requests.exceptions.RequestException as e:
            logger.error("Error checking video status: {}".format(e), exc_info=True)
            raise VideoGenerationError("Failed to check video status: {}".format(e))


class YouTubeClient:
    """Client for YouTube video uploads."""

    def __init__(self):
        self.scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        self.service = None
        logger.info("YouTube client initialized")

    def _get_authenticated_service(self):
        """Get authenticated YouTube service."""
        if self.service:
            return self.service

        try:
            creds = None
            token_path = Path("token.json")
            secrets_path = Path(Config.YOUTUBE_CLIENT_SECRETS_FILE)

            if not secrets_path.exists():
                raise YouTubeUploadError(
                    "YouTube client secrets file not found: {}\n"
                    "Please download it from Google Cloud Console".format(secrets_path)
                )

            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing YouTube credentials")
                    creds.refresh(Request())
                else:
                    logger.info("Starting YouTube OAuth flow")
                    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), self.scopes)
                    creds = flow.run_local_server(port=0)

                with open(token_path, "w") as token:
                    token.write(creds.to_json())
                logger.info("YouTube credentials saved")

            self.service = build("youtube", "v3", credentials=creds)
            logger.info("YouTube service authenticated")
            return self.service

        except Exception as e:
            logger.error("YouTube authentication failed: {}".format(e), exc_info=True)
            raise YouTubeUploadError("Failed to authenticate with YouTube: {}".format(e))

    def upload_video(self, file_path: str, title: str, description: str) -> str:
        """
        Upload video to YouTube.

        Args:
            file_path: Path to video file
            title: Video title (max 100 chars)
            description: Video description

        Returns:
            YouTube video ID

        Raises:
            YouTubeUploadError: If upload fails
        """
        try:
            service = self._get_authenticated_service()

            # Validate file exists
            video_path = Path(file_path)
            if not video_path.exists():
                raise YouTubeUploadError("Video file not found: {}".format(file_path))

            file_size = video_path.stat().st_size
            logger.info("Uploading video: {:.2f} MB".format(file_size / (1024 * 1024)))

            body = {
                "snippet": {
                    "title": title[:100],  # YouTube limit
                    "description": description[:5000],  # YouTube limit
                    "categoryId": Config.YOUTUBE_CATEGORY_ID,
                },
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            }

            media = MediaFileUpload(
                str(video_path), chunksize=1024 * 1024, resumable=True  # 1MB chunks
            )

            request = service.videos().insert(part="snippet,status", body=body, media_body=media)

            response = None
            last_progress = 0
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress - last_progress >= 10:  # Log every 10%
                        logger.info("Upload progress: {}%".format(progress))
                        last_progress = progress

            video_id = response["id"]
            logger.info("Video uploaded successfully: {}".format(video_id))
            return video_id

        except HttpError as e:
            logger.error("YouTube API error: {} - {}".format(e.status_code, e.error_details))
            raise YouTubeUploadError("YouTube upload failed: {}".format(e))
        except Exception as e:
            logger.error("Error uploading to YouTube: {}".format(e), exc_info=True)
            raise YouTubeUploadError("Failed to upload video: {}".format(e))


# --- Main Workflow ---


class StructuredLogger:
    """Handles structured JSON logging to a file."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Create unique log file for this session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / "bot_execution_{}.json".format(timestamp)

        # Initialize the file
        self._write_entry(
            {
                "event": "session_start",
                "timestamp": datetime.now().isoformat(),
                "config": {"log_level": logging.getLevelName(logger.level)},
            }
        )
        logger.info("Structured logging enabled: {}".format(self.log_file))

    def _write_entry(self, data: Dict[str, Any]) -> None:
        """Write a single JSON entry to the log file."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write to structured log: {}".format(e))

    def log_step(
        self,
        chat_id: int,
        step: int,
        name: str,
        status: str,
        input_data: Any = None,
        output_data: Any = None,
        error: str = None,
    ) -> None:
        """Log a workflow step."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "step_execution",
            "chat_id": chat_id,
            "step_number": step,
            "step_name": name,
            "status": status,
        }

        if input_data is not None:
            entry["input"] = input_data
        if output_data is not None:
            entry["output"] = output_data
        if error is not None:
            entry["error"] = error

        self._write_entry(entry)


class WorkflowManager:
    """Manages the complete workflow from Reddit to YouTube."""

    def __init__(self):
        self.json_logger = StructuredLogger()
        self.reddit = RedditClient()
        self.gemini = GeminiClient()
        self.elevenlabs = ElevenLabsClient()
        self.heygen = HeyGenClient()
        self.youtube = YouTubeClient()
        self.active_operations: Dict[int, bool] = {}

    def verify_services(self):
        """Verify all services are accessible and credentials are valid."""
        logger.info("🔍 Verifying services...")

        # 1. Reddit
        try:
            logger.info("Checking Reddit connection...")
            self.reddit.reddit.subreddit("test").id
            logger.info("✅ Reddit connection verified")
        except Exception as e:
            raise ConfigurationError("Reddit verification failed: {}".format(e))

        # 2. Gemini
        try:
            logger.info("Checking Gemini API...")
            self.gemini.model.generate_content("Test", generation_config={"max_output_tokens": 1})
            logger.info("✅ Gemini API verified")
        except Exception as e:
            raise ConfigurationError("Gemini verification failed: {}".format(e))

        # 3. ElevenLabs
        try:
            logger.info("Checking ElevenLabs API...")
            headers = {"xi-api-key": self.elevenlabs.api_key}
            response = requests.get(
                "{}/user".format(self.elevenlabs.base_url), headers=headers, timeout=10
            )
            response.raise_for_status()
            logger.info("✅ ElevenLabs API verified")
        except Exception as e:
            raise ConfigurationError("ElevenLabs verification failed: {}".format(e))

        # 4. HeyGen
        try:
            logger.info("Checking HeyGen API...")
            headers = {"x-api-key": self.heygen.api_key}
            response = requests.head(
                "https://api.heygen.com/v1/user/me", headers=headers, timeout=30
            )
            response.raise_for_status()
            logger.info("✅ HeyGen API verified")
        except Exception as e:
            raise ConfigurationError("HeyGen verification failed: {}".format(e))

        # 5. YouTube
        try:
            logger.info("Checking YouTube credentials...")
            self.youtube._get_authenticated_service()
            logger.info("✅ YouTube credentials verified")
        except Exception as e:
            raise ConfigurationError("YouTube verification failed: {}".format(e))

        logger.info("🎉 All services verified successfully!")

    async def process_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Process a user's Reddit-to-YouTube request.

        Args:
            update: Telegram update object
            context: Telegram context
        """
        message_text = update.message.text
        chat_id = update.effective_chat.id
        status_message = None
        temp_video_path = None

        # Check if operation already in progress
        if chat_id in self.active_operations and self.active_operations[chat_id]:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏳ You already have an operation in progress. Please wait for it to complete.",
            )
            return

        self.active_operations[chat_id] = True
        self.json_logger.log_step(
            chat_id, 0, "process_start", "started", input_data={"message": message_text}
        )

        try:
            # Send initial status message
            status_message = await context.bot.send_message(
                chat_id=chat_id,
                text="🤖 Processing your request...\n\n▪️ Step 1/6: Extracting link information",
            )

            # Step 1: Extract Link Info
            self.json_logger.log_step(
                chat_id, 1, "extract_link_info", "started", input_data=message_text
            )
            link_info = await self.gemini.extract_link_info(message_text)
            self.json_logger.log_step(
                chat_id, 1, "extract_link_info", "completed", output_data=link_info
            )

            subreddit = link_info.get("subReddit")
            post_id = link_info.get("postId")
            user_opinion = link_info.get("text", "")

            if not subreddit or not post_id:
                self.json_logger.log_step(
                    chat_id, 1, "extract_link_info", "failed", error="Missing subreddit or post_id"
                )
                await status_message.edit_text(
                    "❌ Could not extract valid Reddit information from your message.\n\n"
                    "Please send a message like:\n"
                    "https://www.reddit.com/r/subreddit/comments/post_id/\n\n"
                    "You can optionally add your thoughts after the link."
                )
                return

            # Validate Reddit URL format
            if not self._validate_reddit_url(subreddit, post_id):
                self.json_logger.log_step(
                    chat_id, 1, "extract_link_info", "failed", error="Invalid URL format"
                )
                await status_message.edit_text(
                    "❌ Invalid Reddit URL format.\n\n"
                    "Subreddit: r/{}\n"
                    "Post ID: {}\n\n"
                    "Please check the link and try again.".format(subreddit, post_id)
                )
                return

            # Step 2: Fetch Reddit Data
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "▪️ Step 2/6: Fetching Reddit data"
            )

            self.json_logger.log_step(
                chat_id,
                2,
                "fetch_reddit_data",
                "started",
                input_data={"subreddit": subreddit, "post_id": post_id},
            )
            post_data = self.reddit.get_post_data(subreddit, post_id)
            # Log summary of post data to avoid huge logs
            post_data_summary = {k: v for k, v in post_data.items() if k != "comments"}
            post_data_summary["comments_count"] = len(post_data.get("comments", []))
            self.json_logger.log_step(
                chat_id, 2, "fetch_reddit_data", "completed", output_data=post_data_summary
            )

            if not post_data["selftext"] and not post_data["comments"]:
                self.json_logger.log_step(
                    chat_id, 2, "fetch_reddit_data", "failed", error="No content"
                )
                await status_message.edit_text(
                    "❌ This post has no text content or comments to convert.\n"
                    "Please try a different post."
                )
                return

            # Step 3: Generate Script
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "▪️ Step 3/6: Generating script with AI"
            )

            self.json_logger.log_step(
                chat_id, 3, "generate_script", "started", input_data={"user_opinion": user_opinion}
            )
            script_data = await self.gemini.generate_script(
                post_data["selftext"] or post_data["title"], post_data["comments"], user_opinion
            )
            script = script_data["script"]
            title = script_data["title"]
            self.json_logger.log_step(
                chat_id, 3, "generate_script", "completed", output_data=script_data
            )

            # Step 4: Text to Speech
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "✅ Step 3/6: Script generated\n"
                "▪️ Step 4/6: Converting text to speech"
            )

            self.json_logger.log_step(
                chat_id, 4, "text_to_speech", "started", input_data={"script_length": len(script)}
            )
            audio_bytes = self.elevenlabs.text_to_speech(script)
            self.json_logger.log_step(
                chat_id,
                4,
                "text_to_speech",
                "completed",
                output_data={"audio_size": len(audio_bytes)},
            )

            # Step 5: Create Avatar Video
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "✅ Step 3/6: Script generated\n"
                "✅ Step 4/6: Audio created\n"
                "▪️ Step 5/6: Creating avatar video (this takes 5-10 minutes)"
            )

            self.json_logger.log_step(chat_id, 5, "create_avatar_video", "started")
            audio_url = self.heygen.upload_audio(audio_bytes)
            video_id = self.heygen.generate_video(audio_url)
            self.json_logger.log_step(
                chat_id, 5, "create_avatar_video", "in_progress", output_data={"video_id": video_id}
            )

            # Create callback for video status updates
            async def update_video_status(status: str):
                try:
                    await status_message.edit_text(
                        "🤖 Processing your request...\n\n"
                        "✅ Step 1/6: Link extracted\n"
                        "✅ Step 2/6: Reddit data fetched\n"
                        "✅ Step 3/6: Script generated\n"
                        "✅ Step 4/6: Audio created\n"
                        "▪️ Step 5/6: {}".format(status)
                    )
                except Exception as e:
                    logger.warning("Failed to update status message: {}".format(e))

            video_url = await self.heygen.wait_for_video(video_id, update_video_status)
            self.json_logger.log_step(
                chat_id, 5, "create_avatar_video", "completed", output_data={"video_url": video_url}
            )

            # Download video to temporary file
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "✅ Step 3/6: Script generated\n"
                "✅ Step 4/6: Audio created\n"
                "✅ Step 5/6: Video created\n"
                "▪️ Step 6/6: Uploading to YouTube"
            )

            # Use temporary file for video
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                temp_video_path = temp_file.name
                video_response = requests.get(video_url, timeout=300)
                video_response.raise_for_status()
                temp_file.write(video_response.content)
                logger.info("Video downloaded to {}".format(temp_video_path))

            # Step 6: Upload to YouTube
            self.json_logger.log_step(
                chat_id, 6, "upload_youtube", "started", input_data={"title": title}
            )
            youtube_id = self.youtube.upload_video(
                temp_video_path,
                title,
                "{}\n\nSource: {}\n\n#Shorts".format(script, link_info["link"]),
            )
            self.json_logger.log_step(
                chat_id, 6, "upload_youtube", "completed", output_data={"youtube_id": youtube_id}
            )

            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "✅ Step 3/6: Script generated\n"
                "✅ Step 4/6: Audio created\n"
                "✅ Step 5/6: Video created\n"
                "✅ Step 6/6: Uploaded to YouTube"
            )

            # Final success message
            youtube_link = "https://www.youtube.com/watch?v={}".format(youtube_id)
            time.sleep(2)  # Brief pause before final message
            await status_message.edit_text(
                "✅ Video uploaded successfully!\n\n"
                "🎬 Title: {}\n"
                "🔗 Link: {}\n\n"
                "Thanks for using the bot!".format(title, youtube_link)
            )
            self.json_logger.log_step(
                chat_id,
                7,
                "process_complete",
                "success",
                output_data={"youtube_link": youtube_link},
            )

        except RedditAPIError as e:
            logger.error("Reddit API error: {}".format(e))
            self.json_logger.log_step(
                chat_id, -1, "error", "failed", error="RedditAPIError: {}".format(e)
            )
            await self._send_error_message(status_message, chat_id, context, "Reddit Error", str(e))
        except AIGenerationError as e:
            logger.error("AI generation error: {}".format(e))
            self.json_logger.log_step(
                chat_id, -1, "error", "failed", error="AIGenerationError: {}".format(e)
            )
            await self._send_error_message(
                status_message, chat_id, context, "AI Generation Error", str(e)
            )
        except TTSError as e:
            logger.error("TTS error: {}".format(e))
            self.json_logger.log_step(
                chat_id, -1, "error", "failed", error="TTSError: {}".format(e)
            )
            await self._send_error_message(
                status_message, chat_id, context, "Text-to-Speech Error", str(e)
            )
        except VideoGenerationError as e:
            logger.error("Video generation error: {}".format(e))
            self.json_logger.log_step(
                chat_id, -1, "error", "failed", error="VideoGenerationError: {}".format(e)
            )
            await self._send_error_message(
                status_message, chat_id, context, "Video Generation Error", str(e)
            )
        except YouTubeUploadError as e:
            logger.error("YouTube upload error: {}".format(e))
            self.json_logger.log_step(
                chat_id, -1, "error", "failed", error="YouTubeUploadError: {}".format(e)
            )
            await self._send_error_message(
                status_message, chat_id, context, "YouTube Upload Error", str(e)
            )
        except Exception as e:
            logger.error("Unexpected error processing request: {}".format(e), exc_info=True)
            self.json_logger.log_step(
                chat_id, -1, "error", "failed", error="UnexpectedError: {}".format(e)
            )
            await self._send_error_message(
                status_message,
                chat_id,
                context,
                "Unexpected Error",
                "An unexpected error occurred: {}".format(str(e)),
            )
        finally:
            # Cleanup
            self.active_operations[chat_id] = False

            if temp_video_path and Path(temp_video_path).exists():
                try:
                    Path(temp_video_path).unlink()
                    logger.info("Cleaned up temporary video: {}".format(temp_video_path))
                except Exception as e:
                    logger.warning("Failed to cleanup temp file: {}".format(e))

    @staticmethod
    def _validate_reddit_url(subreddit: str, post_id: str) -> bool:
        """Validate Reddit URL components."""
        # Subreddit: alphanumeric and underscores, 3-21 chars
        if not re.match(r"^[a-zA-Z0-9_]{3,21}$", subreddit):
            return False
        # Post ID: alphanumeric, 6-7 chars
        if not re.match(r"^[a-z0-9]{6,7}$", post_id):
            return False
        return True

    @staticmethod
    async def _send_error_message(
        status_message, chat_id: int, context, error_type: str, error_detail: str
    ):
        """Send formatted error message to user."""
        error_text = (
            "❌ {}\n\n"
            "{}\n\n"
            "Please try again or contact support if the issue persists.".format(
                error_type, error_detail
            )
        )

        if status_message:
            try:
                await status_message.edit_text(error_text)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=error_text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_text)


# --- Bot Setup ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    welcome_message = (
        "👋 Welcome to Reddit to YouTube Automation Bot!\n\n"
        "🎥 I can turn Reddit posts into AI avatar videos and upload them to YouTube.\n\n"
        "How to use:\n"
        "   1. Send me a Reddit link\n"
        "   2. Optionally add your thoughts/opinion\n"
        "   3. Wait 5-10 minutes for processing\n"
        "   4. Get your YouTube link!\n\n"
        "Example:\n"
        "`https://www.reddit.com/r/technology/comments/abc123/`\n\n"
        "`https://www.reddit.com/r/askreddit/comments/xyz789/ This is interesting because...`\n\n"
        "Note: Processing uses paid APIs (ElevenLabs, HeyGen). "
        "Make sure you have sufficient credits.\n\n"
        "Send me a Reddit link to get started!"
    )
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "Reddit to YouTube Bot Help\n\n"
        "Commands:\n"
        "   • /start - Show welcome message\n"
        "   • /help - Show this help message\n\n"
        "Process Steps:\n"
        "   1. Extract link from your message\n"
        "   2. Fetch Reddit post and comments\n"
        "   3. Generate script with AI\n"
        "   4. Convert to speech (ElevenLabs)\n"
        "   5. Create avatar video (HeyGen)\n"
        "   6. Upload to YouTube\n\n"
        "Tips:\n"
        "   • Use posts with good discussion\n"
        "   • Processing takes 5-10 minutes\n"
        "   • Only one operation per user at a time\n"
        "   • Check your API credits before starting\n\n"
        "Estimated Costs:\n"
        "   • ElevenLabs: ~$0.05-0.15 per video\n"
        "   • HeyGen: ~$0.10-0.50 per video\n"
        "   • Total: ~$0.15-0.65 per video"
    )
    await update.message.reply_text(help_text)


def main():
    """Main entry point."""
    try:
        # Validate configuration
        Config.validate_and_load()

        # Initialize workflow manager and services first
        logger.info("Initializing services...")
        workflow = WorkflowManager()

        # Verify all services are working
        workflow.verify_services()

        # Build application
        application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, workflow.process_request)
        )

        logger.info("🤖 Bot is starting...")
        logger.info("Press Ctrl+C to stop")

        # Run bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except ConfigurationError as e:
        logger.error("Configuration error: {}".format(e))
        print("\n❌ Configuration Error:\n{}\n".format(e))
        print("Please check your .env file. See .env.example for reference.")
        return 1
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        return 0
    except Exception as e:
        logger.error("Fatal error: {}".format(e), exc_info=True)
        print("\n❌ Fatal Error:\n{}\n".format(e))
        return 1


if __name__ == "__main__":
    exit(main())
