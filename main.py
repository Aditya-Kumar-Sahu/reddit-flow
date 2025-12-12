import os
import json
import time
import asyncio
import logging
import re
import tempfile
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

import requests
import praw
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Google API imports for YouTube
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO'))
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
    SCRIPT_MAX_WORDS: int = 175
    HEYGEN_WAIT_TIMEOUT: int = 1800  # 30 minutes
    HEYGEN_VIDEO_WIDTH: int = 1280
    HEYGEN_VIDEO_HEIGHT: int = 720
    
    # Constants
    REDDIT_URL_PATTERN = re.compile(
        r'reddit\.com/r/([^/]+)/comments/([a-z0-9]+)'
    )
    
    @classmethod
    def validate_and_load(cls) -> None:
        """Validate all required environment variables are set."""
        required_vars = [
            'TELEGRAM_BOT_TOKEN',
            'REDDIT_CLIENT_ID',
            'REDDIT_CLIENT_SECRET',
            'REDDIT_USER_AGENT',
            'GOOGLE_API_KEY',
            'ELEVENLABS_API_KEY',
            'ELEVENLABS_VOICE_ID',
            'HEYGEN_API_KEY',
            'HEYGEN_AVATAR_ID',
            'YOUTUBE_CLIENT_SECRETS_FILE'
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
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                f"Please check your .env file. See .env.example for reference."
            )
        
        # Load optional configuration
        cls.YOUTUBE_CATEGORY_ID = os.getenv('YOUTUBE_CATEGORY_ID', cls.YOUTUBE_CATEGORY_ID)
        cls.YOUTUBE_REGION_CODE = os.getenv('YOUTUBE_REGION_CODE', cls.YOUTUBE_REGION_CODE)
        cls.MAX_COMMENTS = int(os.getenv('MAX_COMMENTS', cls.MAX_COMMENTS))
        cls.SCRIPT_MAX_WORDS = int(os.getenv('SCRIPT_MAX_WORDS', cls.SCRIPT_MAX_WORDS))
        cls.HEYGEN_WAIT_TIMEOUT = int(os.getenv('HEYGEN_WAIT_TIMEOUT', cls.HEYGEN_WAIT_TIMEOUT))
        cls.HEYGEN_VIDEO_WIDTH = int(os.getenv('HEYGEN_VIDEO_WIDTH', cls.HEYGEN_VIDEO_WIDTH))
        cls.HEYGEN_VIDEO_HEIGHT = int(os.getenv('HEYGEN_VIDEO_HEIGHT', cls.HEYGEN_VIDEO_HEIGHT))
        
        logger.info("Configuration validated successfully")


# --- Service Classes ---

class RedditClient:
    """Client for interacting with Reddit API."""
    
    def __init__(self):
        try:
            self.reddit = praw.Reddit(
                client_id=Config.REDDIT_CLIENT_ID,
                client_secret=Config.REDDIT_CLIENT_SECRET,
                user_agent=Config.REDDIT_USER_AGENT
            )
            logger.info("Reddit client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise RedditAPIError(f"Reddit initialization failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, praw.exceptions.PRAWException))
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
            logger.info(f"Fetching post r/{subreddit_name}/{post_id}")
            submission = self.reddit.submission(id=post_id)
            
            # Load some comment replies (limited to avoid excessive loading)
            submission.comments.replace_more(limit=5)
            
            post_data = {
                "title": submission.title,
                "selftext": submission.selftext or "",
                "url": submission.url,
                "author": str(submission.author) if submission.author else "[deleted]",
                "score": submission.score,
                "comments": self._extract_comments(submission.comments.list()[:50])  # Limit initial comments
            }
            
            logger.info(f"Fetched post with {len(post_data['comments'])} comments")
            return post_data
            
        except praw.exceptions.InvalidURL:
            raise RedditAPIError(f"Invalid Reddit post: r/{subreddit_name}/comments/{post_id}")
        except praw.exceptions.NotFound:
            raise RedditAPIError(f"Post not found: r/{subreddit_name}/comments/{post_id}")
        except Exception as e:
            logger.error(f"Error fetching Reddit post: {e}", exc_info=True)
            raise RedditAPIError(f"Failed to fetch Reddit post: {e}")

    def _extract_comments(self, comments: List, depth: int = 0, max_depth: int = 3) -> List[Dict]:
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
                    "score": comment.score
                }
                
                all_content.append(content)
                
                # Recursively extract replies
                if hasattr(comment, 'replies') and len(comment.replies) > 0:
                    reply_list = comment.replies.list()[:10]  # Limit replies per comment
                    all_content.extend(self._extract_comments(reply_list, depth + 1, max_depth))
                    
            except Exception as e:
                logger.warning(f"Error extracting comment {getattr(comment, 'id', 'unknown')}: {e}")
                continue
        
        return all_content


class GeminiClient:
    """Client for Google Gemini AI operations."""
    
    def __init__(self):
        try:
            genai.configure(api_key=Config.GOOGLE_API_KEY)
            # Try one of these newer models
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            # OR
            # self.model = genai.GenerativeModel('gemini-1.5-pro')
            logger.info("Gemini client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise AIGenerationError(f"Gemini initialization failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
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
            prompt = f"""
            Extract the Reddit link, subreddit, post ID, and any additional user text from this message:
            "{message_text}"
            
            Return JSON with keys: link, subReddit, postId, text.
            If no additional text is provided, set 'text' to null.
            Example JSON format:
            {{
                "link": "https://www.reddit.com/r/sheffield/comments/1nf7kh6/guys_the_impossible_happened/",
                "subReddit": "sheffield",
                "postId": "1nf7kh6",
                "text": "text provided by the user other than the link, this can be null"
            }}
            """
            
            logger.debug("Extracting link info with Gemini")
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()
            
            # Clean up markdown code blocks if present
            text = self._clean_json_response(text)
            
            result = json.loads(text)
            
            # Validate required fields
            if not all(key in result for key in ['link', 'subReddit', 'postId']):
                raise ValueError("Missing required fields in AI response")
            
            logger.info(f"Extracted link info for r/{result['subReddit']}/{result['postId']}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {text}")
            raise AIGenerationError(f"Invalid JSON from AI: {e}")
        except Exception as e:
            logger.error(f"Error extracting link info: {e}", exc_info=True)
            raise AIGenerationError(f"Failed to extract link information: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def generate_script(self, post_text: str, comments_data: List[Dict], user_opinion: Optional[str]) -> Dict[str, str]:
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
            limited_comments = comments_data[:Config.MAX_COMMENTS]
            comments_str = json.dumps(limited_comments, indent=2)
            
            system_prompt = f"""
            You are an expert script writer for social media content.
            
            ## Writing Instructions:
            Write a script for a short-form video for a broad audience. Do not use emojis in the script, and avoid Gen Z slang. 
            The script should be less than {Config.SCRIPT_MAX_WORDS} words with an engaging hook and interactive CTA.
            
            Write like a confident, clear-thinking human speaking to another smart human.
            Avoid robotic phrases like 'in today's fast-paced world', 'leveraging synergies', or 'furthermore'.
            Skip unnecessary dashes (—), quotation marks (""), and corporate buzzwords like 'cutting-edge', 'robust', or 'seamless experience'.
            
            No AI tone. No fluff. No filler.
            Use natural transitions like 'here's the thing', 'let's break it down', or 'what this really means is…'
            Keep sentences varied in length and rhythm, like how real people speak or write.
            Prioritize clarity, personality, and usefulness. Every sentence should feel intentional, not generated.
            Do not ask questions and then answer them yourself.
            Do not describe scenes, just write the speaking script without any markdown.
            """
            
            user_prompt = f"""
            Post Content: {post_text}
            
            Comments: {comments_str}
            
            User Opinion: {user_opinion or 'None provided'}
            
            Generate a video script and title based on this Reddit content.
            Return JSON with keys: 'script' and 'title'.
            """
            
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            
            logger.debug("Generating script with Gemini")
            response = await self.model.generate_content_async(full_prompt)
            text = response.text.strip()
            
            text = self._clean_json_response(text)
            result = json.loads(text)
            
            # Validate response structure
            if 'script' not in result or 'title' not in result:
                raise ValueError("Missing script or title in AI response")
            
            # Validate script length
            word_count = len(result['script'].split())
            if word_count > Config.SCRIPT_MAX_WORDS * 1.2:  # Allow 20% overflow
                logger.warning(f"Script length ({word_count} words) exceeds limit")
            
            logger.info(f"Generated script: {word_count} words, title: {result['title'][:50]}...")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {text}")
            raise AIGenerationError(f"Invalid JSON from AI: {e}")
        except Exception as e:
            logger.error(f"Error generating script: {e}", exc_info=True)
            raise AIGenerationError(f"Failed to generate script: {e}")
    
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
        retry=retry_if_exception_type(requests.exceptions.RequestException)
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
            url = f"{self.base_url}/text-to-speech/{self.voice_id}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            
            logger.debug(f"Converting {len(text)} characters to speech")
            response = requests.post(url, json=data, headers=headers, timeout=60)
            response.raise_for_status()
            
            audio_size = len(response.content)
            logger.info(f"Generated audio: {audio_size / 1024:.2f} KB")
            return response.content
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"ElevenLabs API error: {e.response.status_code} - {e.response.text}")
            raise TTSError(f"Text-to-speech conversion failed: {e}")
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}", exc_info=True)
            raise TTSError(f"Failed to convert text to speech: {e}")


class HeyGenClient:
    """Client for HeyGen avatar video generation."""
    
    def __init__(self):
        self.api_key = Config.HEYGEN_API_KEY
        self.avatar_id = Config.HEYGEN_AVATAR_ID
        self.base_url = "https://api.heygen.com"
        self.upload_url = "https://upload.heygen.com/v1/asset"
        logger.info("HeyGen client initialized")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException)
    )
    def upload_audio(self, audio_data: bytes) -> str:
        """
        Upload audio to HeyGen.
        
        Args:
            audio_data: Audio file bytes
            
        Returns:
            URL of uploaded audio
            
        Raises:
            VideoGenerationError: If upload fails
        """
        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "audio/mpeg"
            }
            
            logger.debug(f"Uploading {len(audio_data) / 1024:.2f} KB audio to HeyGen")
            response = requests.post(self.upload_url, data=audio_data, headers=headers, timeout=120)
            response.raise_for_status()
            
            audio_url = response.json()["data"]["url"]
            logger.info(f"Audio uploaded successfully: {audio_url}")
            return audio_url
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HeyGen upload error: {e.response.status_code} - {e.response.text}")
            raise VideoGenerationError(f"Audio upload failed: {e}")
        except Exception as e:
            logger.error(f"Error uploading audio: {e}", exc_info=True)
            raise VideoGenerationError(f"Failed to upload audio: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException)
    )
    def generate_video(self, audio_url: str) -> str:
        """
        Start avatar video generation.
        
        Args:
            audio_url: URL of uploaded audio
            
        Returns:
            Video ID for tracking generation
            
        Raises:
            VideoGenerationError: If video generation request fails
        """
        try:
            url = f"{self.base_url}/v2/video/generate"
            headers = {
                "X-Api-Key": self.api_key,
                "Content-Type": "application/json"
            }
            data = {
                "video_inputs": [
                    {
                        "character": {
                            "type": "avatar",
                            "avatar_id": self.avatar_id,
                            "avatar_style": "normal"
                        },
                        "voice": {
                            "type": "audio",
                            "audio_url": audio_url
                        }
                    }
                ],
                "test": False,
                "caption": False,
                "dimension": {
                    "width": Config.HEYGEN_VIDEO_WIDTH,
                    "height": Config.HEYGEN_VIDEO_HEIGHT
                }
            }
            
            logger.debug("Requesting HeyGen video generation")
            response = requests.post(url, json=data, headers=headers, timeout=60)
            response.raise_for_status()
            
            video_id = response.json()["data"]["video_id"]
            logger.info(f"Video generation started: {video_id}")
            return video_id
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HeyGen generation error: {e.response.status_code} - {e.response.text}")
            raise VideoGenerationError(f"Video generation failed: {e}")
        except Exception as e:
            logger.error(f"Error generating video: {e}", exc_info=True)
            raise VideoGenerationError(f"Failed to start video generation: {e}")

    async def wait_for_video(self, video_id: str, update_callback=None) -> str:
        """
        Wait for video generation to complete with timeout.
        
        Args:
            video_id: HeyGen video ID
            update_callback: Optional async callback for status updates
            
        Returns:
            URL of completed video
            
        Raises:
            VideoGenerationError: If video generation fails or times out
        """
        url = f"{self.base_url}/v1/video_status.get"
        headers = {
            "x-api-key": self.api_key,
            "accept": "application/json"
        }
        
        start_time = time.time()
        attempt = 0
        wait_time = 10  # Start with 10 seconds
        max_wait_time = 60  # Max 60 seconds between checks
        
        try:
            while True:
                elapsed = time.time() - start_time
                
                # Check timeout
                if elapsed > Config.HEYGEN_WAIT_TIMEOUT:
                    raise VideoGenerationError(
                        f"Video generation timed out after {Config.HEYGEN_WAIT_TIMEOUT} seconds"
                    )
                
                attempt += 1
                logger.debug(f"Checking video status (attempt {attempt}, elapsed: {elapsed:.0f}s)")
                
                response = requests.get(
                    url,
                    params={"video_id": video_id},
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()["data"]
                status = data["status"]
                
                if status == "completed":
                    video_url = data["video_url"]
                    logger.info(f"Video completed after {elapsed:.0f}s: {video_url}")
                    return video_url
                    
                elif status == "failed":
                    error = data.get('error', 'Unknown error')
                    logger.error(f"HeyGen video generation failed: {error}")
                    raise VideoGenerationError(f"Video generation failed: {error}")
                
                # Send status update via callback
                if update_callback:
                    await update_callback(f"Video generation: {status} ({elapsed:.0f}s elapsed)")
                
                logger.info(f"Video status: {status}, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                
                # Exponential backoff
                wait_time = min(wait_time * 1.5, max_wait_time)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking video status: {e}", exc_info=True)
            raise VideoGenerationError(f"Failed to check video status: {e}")


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
                    f"YouTube client secrets file not found: {secrets_path}\n"
                    "Please download it from Google Cloud Console"
                )
            
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing YouTube credentials")
                    creds.refresh(Request())
                else:
                    logger.info("Starting YouTube OAuth flow")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(secrets_path), self.scopes
                    )
                    creds = flow.run_local_server(port=0)
                
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
                logger.info("YouTube credentials saved")
            
            self.service = build("youtube", "v3", credentials=creds)
            logger.info("YouTube service authenticated")
            return self.service
            
        except Exception as e:
            logger.error(f"YouTube authentication failed: {e}", exc_info=True)
            raise YouTubeUploadError(f"Failed to authenticate with YouTube: {e}")

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
                raise YouTubeUploadError(f"Video file not found: {file_path}")
            
            file_size = video_path.stat().st_size
            logger.info(f"Uploading video: {file_size / (1024*1024):.2f} MB")
            
            body = {
                "snippet": {
                    "title": title[:100],  # YouTube limit
                    "description": description[:5000],  # YouTube limit
                    "categoryId": Config.YOUTUBE_CATEGORY_ID
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(
                str(video_path),
                chunksize=1024*1024,  # 1MB chunks
                resumable=True
            )
            
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            last_progress = 0
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress - last_progress >= 10:  # Log every 10%
                        logger.info(f"Upload progress: {progress}%")
                        last_progress = progress

            video_id = response["id"]
            logger.info(f"Video uploaded successfully: {video_id}")
            return video_id
            
        except HttpError as e:
            logger.error(f"YouTube API error: {e.status_code} - {e.error_details}")
            raise YouTubeUploadError(f"YouTube upload failed: {e}")
        except Exception as e:
            logger.error(f"Error uploading to YouTube: {e}", exc_info=True)
            raise YouTubeUploadError(f"Failed to upload video: {e}")


# --- Main Workflow ---

class WorkflowManager:
    """Manages the complete workflow from Reddit to YouTube."""
    
    def __init__(self):
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
            self.reddit.reddit.subreddit("all").id
            logger.info("✅ Reddit connection verified")
        except Exception as e:
            raise ConfigurationError(f"Reddit verification failed: {e}")

        # 2. Gemini
        try:
            logger.info("Checking Gemini API...")
            self.gemini.model.generate_content("Test", generation_config={"max_output_tokens": 1})
            logger.info("✅ Gemini API verified")
        except Exception as e:
            raise ConfigurationError(f"Gemini verification failed: {e}")

        # 3. ElevenLabs
        try:
            logger.info("Checking ElevenLabs API...")
            headers = {"xi-api-key": self.elevenlabs.api_key}
            response = requests.get(f"{self.elevenlabs.base_url}/user", headers=headers, timeout=10)
            response.raise_for_status()
            logger.info("✅ ElevenLabs API verified")
        except Exception as e:
            raise ConfigurationError(f"ElevenLabs verification failed: {e}")

        # 4. HeyGen
        try:
            logger.info("Checking HeyGen API...")
            headers = {"x-api-key": self.heygen.api_key}
            response = requests.get("https://api.heygen.com/v2/avatars", headers=headers, timeout=10)
            response.raise_for_status()
            logger.info("✅ HeyGen API verified")
        except Exception as e:
            raise ConfigurationError(f"HeyGen verification failed: {e}")

        # 5. YouTube
        try:
            logger.info("Checking YouTube credentials...")
            self.youtube._get_authenticated_service()
            logger.info("✅ YouTube credentials verified")
        except Exception as e:
            raise ConfigurationError(f"YouTube verification failed: {e}")
            
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
                text="⏳ You already have an operation in progress. Please wait for it to complete."
            )
            return
        
        self.active_operations[chat_id] = True
        
        try:
            # Send initial status message
            status_message = await context.bot.send_message(
                chat_id=chat_id,
                text="🤖 Processing your request...\n\n▪️ Step 1/6: Extracting link information"
            )
            
            # Step 1: Extract Link Info
            link_info = await self.gemini.extract_link_info(message_text)
            subreddit = link_info.get("subReddit")
            post_id = link_info.get("postId")
            user_opinion = link_info.get("text", "")
            
            if not subreddit or not post_id:
                await status_message.edit_text(
                    "❌ Could not extract valid Reddit information from your message.\n\n"
                    "Please send a message like:\n"
                    "https://www.reddit.com/r/subreddit/comments/post_id/\n\n"
                    "You can optionally add your thoughts after the link."
                )
                return
            
            # Validate Reddit URL format
            if not self._validate_reddit_url(subreddit, post_id):
                await status_message.edit_text(
                    "❌ Invalid Reddit URL format.\n\n"
                    f"Subreddit: r/{subreddit}\n"
                    f"Post ID: {post_id}\n\n"
                    "Please check the link and try again."
                )
                return

            # Step 2: Fetch Reddit Data
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "▪️ Step 2/6: Fetching Reddit data"
            )
            
            post_data = self.reddit.get_post_data(subreddit, post_id)
            
            if not post_data["selftext"] and not post_data["comments"]:
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
            
            script_data = await self.gemini.generate_script(
                post_data["selftext"] or post_data["title"],
                post_data["comments"],
                user_opinion
            )
            script = script_data["script"]
            title = script_data["title"]
            
            # Step 4: Text to Speech
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "✅ Step 3/6: Script generated\n"
                "▪️ Step 4/6: Converting text to speech"
            )
            
            audio_bytes = self.elevenlabs.text_to_speech(script)
            
            # Step 5: Create Avatar Video
            await status_message.edit_text(
                "🤖 Processing your request...\n\n"
                "✅ Step 1/6: Link extracted\n"
                "✅ Step 2/6: Reddit data fetched\n"
                "✅ Step 3/6: Script generated\n"
                "✅ Step 4/6: Audio created\n"
                "▪️ Step 5/6: Creating avatar video (this takes 2-5 minutes)"
            )
            
            audio_url = self.heygen.upload_audio(audio_bytes)
            video_id = self.heygen.generate_video(audio_url)
            
            # Create callback for video status updates
            async def update_video_status(status: str):
                try:
                    await status_message.edit_text(
                        "🤖 Processing your request...\n\n"
                        "✅ Step 1/6: Link extracted\n"
                        "✅ Step 2/6: Reddit data fetched\n"
                        "✅ Step 3/6: Script generated\n"
                        "✅ Step 4/6: Audio created\n"
                        f"▪️ Step 5/6: {status}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to update status message: {e}")
            
            video_url = await self.heygen.wait_for_video(video_id, update_video_status)
            
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
                logger.info(f"Video downloaded to {temp_video_path}")
            
            # Step 6: Upload to YouTube
            youtube_id = self.youtube.upload_video(
                temp_video_path,
                title,
                f"{script}\n\nSource: {link_info['link']}"
            )
            
            # Final success message
            youtube_link = f"https://www.youtube.com/watch?v={youtube_id}"
            await status_message.edit_text(
                "✅ **Video uploaded successfully!**\n\n"
                f"🎬 Title: {title}\n"
                f"🔗 Link: {youtube_link}\n\n"
                "Thanks for using the bot!"
            )

        except RedditAPIError as e:
            logger.error(f"Reddit API error: {e}")
            await self._send_error_message(status_message, chat_id, context, 
                "Reddit Error", str(e))
        except AIGenerationError as e:
            logger.error(f"AI generation error: {e}")
            await self._send_error_message(status_message, chat_id, context,
                "AI Generation Error", str(e))
        except TTSError as e:
            logger.error(f"TTS error: {e}")
            await self._send_error_message(status_message, chat_id, context,
                "Text-to-Speech Error", str(e))
        except VideoGenerationError as e:
            logger.error(f"Video generation error: {e}")
            await self._send_error_message(status_message, chat_id, context,
                "Video Generation Error", str(e))
        except YouTubeUploadError as e:
            logger.error(f"YouTube upload error: {e}")
            await self._send_error_message(status_message, chat_id, context,
                "YouTube Upload Error", str(e))
        except Exception as e:
            logger.error(f"Unexpected error processing request: {e}", exc_info=True)
            await self._send_error_message(status_message, chat_id, context,
                "Unexpected Error", f"An unexpected error occurred: {str(e)}")
        finally:
            # Cleanup
            self.active_operations[chat_id] = False
            
            if temp_video_path and Path(temp_video_path).exists():
                try:
                    Path(temp_video_path).unlink()
                    logger.info(f"Cleaned up temporary video: {temp_video_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")
    
    @staticmethod
    def _validate_reddit_url(subreddit: str, post_id: str) -> bool:
        """Validate Reddit URL components."""
        # Subreddit: alphanumeric and underscores, 3-21 chars
        if not re.match(r'^[a-zA-Z0-9_]{3,21}$', subreddit):
            return False
        # Post ID: alphanumeric, 6-7 chars
        if not re.match(r'^[a-z0-9]{6,7}$', post_id):
            return False
        return True
    
    @staticmethod
    async def _send_error_message(status_message, chat_id: int, context, error_type: str, error_detail: str):
        """Send formatted error message to user."""
        error_text = (
            f"❌ **{error_type}**\n\n"
            f"{error_detail}\n\n"
            "Please try again or contact support if the issue persists."
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
        "👋 **Welcome to Reddit to YouTube Automation Bot!**\n\n"
        "🎥 I can turn Reddit posts into AI avatar videos and upload them to YouTube.\n\n"
        "**How to use:**\n"
        "1. Send me a Reddit link\n"
        "2. Optionally add your thoughts/opinion\n"
        "3. Wait 5-10 minutes for processing\n"
        "4. Get your YouTube link!\n\n"
        "**Example:**\n"
        "`https://www.reddit.com/r/technology/comments/abc123/`\n\n"
        "`https://www.reddit.com/r/askreddit/comments/xyz789/ This is interesting because...`\n\n"
        "**Note:** Processing uses paid APIs (ElevenLabs, HeyGen). "
        "Make sure you have sufficient credits.\n\n"
        "Send me a Reddit link to get started!"
    )
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "**Reddit to YouTube Bot Help**\n\n"
        "**Commands:**\n"
        "• /start - Show welcome message\n"
        "• /help - Show this help message\n\n"
        "**Process Steps:**\n"
        "1. Extract link from your message\n"
        "2. Fetch Reddit post and comments\n"
        "3. Generate script with AI\n"
        "4. Convert to speech (ElevenLabs)\n"
        "5. Create avatar video (HeyGen)\n"
        "6. Upload to YouTube\n\n"
        "**Tips:**\n"
        "• Use posts with good discussion\n"
        "• Processing takes 5-10 minutes\n"
        "• Only one operation per user at a time\n"
        "• Check your API credits before starting\n\n"
        "**Estimated Costs:**\n"
        "• ElevenLabs: ~$0.05-0.15 per video\n"
        "• HeyGen: ~$0.10-0.50 per video\n"
        "• Total: ~$0.15-0.65 per video"
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
        logger.error(f"Configuration error: {e}")
        print(f"\n❌ Configuration Error:\n{e}\n")
        print("Please check your .env file. See .env.example for reference.")
        return 1
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal Error:\n{e}\n")
        return 1


if __name__ == '__main__':
    exit(main())
