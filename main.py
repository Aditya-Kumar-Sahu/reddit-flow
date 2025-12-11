import os
import json
import time
import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
import praw
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from tenacity import retry, stop_after_attempt, wait_exponential

# Google API imports for YouTube
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
    YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
    
    # Constants from n8n workflow
    ELEVENLABS_VOICE_ID = "SCGpjQlJ86We8EYPpWB4Ffff"
    HEYGEN_AVATAR_ID = "1c51d2d27rered514c7ea51781f71b325d2c"
    YOUTUBE_CATEGORY_ID = "28"  # Science & Technology
    YOUTUBE_REGION_CODE = "IN"

# --- Service Classes ---

class RedditClient:
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=Config.REDDIT_CLIENT_ID,
            client_secret=Config.REDDIT_CLIENT_SECRET,
            user_agent=Config.REDDIT_USER_AGENT
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_post_data(self, subreddit_name: str, post_id: str) -> Dict[str, Any]:
        submission = self.reddit.submission(id=post_id)
        
        # Ensure comments are loaded
        submission.comments.replace_more(limit=None)
        
        post_data = {
            "title": submission.title,
            "selftext": submission.selftext,
            "url": submission.url,
            "author": str(submission.author),
            "score": submission.score,
            "comments": self._extract_comments(submission.comments)
        }
        return post_data

    def _extract_comments(self, comments_forest, all_content=None) -> List[Dict]:
        if all_content is None:
            all_content = []
            
        for comment in comments_forest:
            if isinstance(comment, praw.models.MoreComments):
                continue
                
            content = {
                "id": comment.id,
                "body": comment.body,
                "author": str(comment.author),
                "depth": comment.depth,
                "parent_id": comment.parent_id,
                "has_replies": False,
                "reply_count": 0
            }
            
            if len(comment.replies) > 0:
                content["has_replies"] = True
                content["reply_count"] = len(comment.replies)
                self._extract_comments(comment.replies, all_content)
            
            all_content.append(content)
            
        return all_content

class GeminiClient:
    def __init__(self):
        genai.configure(api_key=Config.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def extract_link_info(self, message_text: str) -> Dict[str, str]:
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
        response = await self.model.generate_content_async(prompt)
        text = response.text.strip()
        # Clean up markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
        return json.loads(text)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def generate_script(self, post_text: str, comments_data: List[Dict], user_opinion: str) -> Dict[str, str]:
        comments_str = json.dumps(comments_data[:20]) # Limit comments to avoid token limits
        
        system_prompt = """
        You are the best script writer; your task is to write a script using the Reddit texts and the opinion provided. 

        ---
        ## Writing Instructions:
        Write a script for an Instagram reel for a broad range of audiences. Do not use emojis in the script, and also don't use Gen Z slang. The human will provide you with the context, and you need to write a script based on it and anything related to it. The script should be less than 175 words with an engaging hook and interactive CTA.

        Write like a confident, clear-thinking human speaking to another smart human.
        Avoid robotic phrases like ‘in today’s fast-paced world’, ‘leveraging synergies’, or ‘furthermore’.
        Skip unnecessary dashes (—), quotation marks (“”), and corporate buzzwords like ‘cutting-edge’, ‘robust’, or ‘seamless experience’.

        No AI tone. No fluff. No filler.
        Use natural transitions like ‘here’s the thing’, ‘let’s break it down’, or ‘what this really means is…’
        Keep sentences varied in length and rhythm, like how real people speak or write.
        Prioritize clarity, personality, and usefulness. Every sentence should feel intentional, not generated.
        No, asking questions and answering yourself.
        Do not describe the scences, just write the speaking script without any markdown nothing else. Do not include \\n in the script.
        """
        
        user_prompt = f"{post_text} {comments_str} Opinion: {user_opinion}"
        
        full_prompt = f"{system_prompt}\n\nContext:\n{user_prompt}\n\nReturn JSON with keys: 'script' and 'title'."
        
        response = await self.model.generate_content_async(full_prompt)
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
            
        return json.loads(text)

class ElevenLabsClient:
    def __init__(self):
        self.api_key = Config.ELEVENLABS_API_KEY
        self.base_url = "https://api.elevenlabs.io/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def text_to_speech(self, text: str) -> bytes:
        url = f"{self.base_url}/text-to-speech/{Config.ELEVENLABS_VOICE_ID}"
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
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.content

class HeyGenClient:
    def __init__(self):
        self.api_key = Config.HEYGEN_API_KEY
        self.base_url = "https://api.heygen.com"
        self.upload_url = "https://upload.heygen.com/v1/asset"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def upload_audio(self, audio_data: bytes) -> str:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "audio/mpeg"
        }
        response = requests.post(self.upload_url, data=audio_data, headers=headers)
        response.raise_for_status()
        return response.json()["data"]["url"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_video(self, audio_url: str) -> str:
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
                        "avatar_id": Config.HEYGEN_AVATAR_ID,
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
                "width": 1280,
                "height": 720
            }
        }
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()["data"]["video_id"]

    async def wait_for_video(self, video_id: str) -> str:
        url = f"{self.base_url}/v1/video_status.get"
        headers = {
            "x-api-key": self.api_key,
            "accept": "application/json"
        }
        
        while True:
            response = requests.get(url, params={"video_id": video_id}, headers=headers)
            response.raise_for_status()
            data = response.json()["data"]
            status = data["status"]
            
            if status == "completed":
                return data["video_url"]
            elif status == "failed":
                raise Exception(f"HeyGen video generation failed: {data.get('error')}")
            
            logger.info(f"HeyGen video status: {status}. Waiting...")
            await asyncio.sleep(30)

class YouTubeClient:
    def __init__(self):
        self.scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        self.service = self._get_authenticated_service()

    def _get_authenticated_service(self):
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", self.scopes)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    Config.YOUTUBE_CLIENT_SECRETS_FILE, self.scopes)
                creds = flow.run_local_server(port=0)
            
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        return build("youtube", "v3", credentials=creds)

    def upload_video(self, file_path: str, title: str, description: str) -> str:
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "categoryId": Config.YOUTUBE_CATEGORY_ID
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Uploaded {int(status.progress() * 100)}%")

        return response["id"]

# --- Main Workflow ---

class WorkflowManager:
    def __init__(self):
        self.reddit = RedditClient()
        self.gemini = GeminiClient()
        self.elevenlabs = ElevenLabsClient()
        self.heygen = HeyGenClient()
        self.youtube = YouTubeClient()

    async def process_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message_text = update.message.text
        chat_id = update.effective_chat.id
        
        await context.bot.send_message(chat_id=chat_id, text="🤖 Processing your request... Step 1: Extracting Link Info")
        
        try:
            # 1. Extract Link Info
            link_info = await self.gemini.extract_link_info(message_text)
            subreddit = link_info.get("subReddit")
            post_id = link_info.get("postId")
            user_opinion = link_info.get("text", "")
            
            if not subreddit or not post_id:
                await context.bot.send_message(chat_id=chat_id, text="❌ Could not extract Reddit info. Please check the link.")
                return

            # 2. Fetch Reddit Data
            await context.bot.send_message(chat_id=chat_id, text="📥 Step 2: Fetching Reddit Data")
            post_data = self.reddit.get_post_data(subreddit, post_id)
            
            # 3. Generate Script
            await context.bot.send_message(chat_id=chat_id, text="✍️ Step 3: Generating Script")
            script_data = await self.gemini.generate_script(
                post_data["selftext"], 
                post_data["comments"], 
                user_opinion
            )
            script = script_data["script"]
            title = script_data["title"]
            
            # 4. Text to Speech
            await context.bot.send_message(chat_id=chat_id, text="🗣️ Step 4: Converting Text to Speech")
            audio_bytes = self.elevenlabs.text_to_speech(script)
            
            # 5. Create Avatar Video
            await context.bot.send_message(chat_id=chat_id, text="🎥 Step 5: Creating Avatar Video (This may take a few minutes)")
            audio_url = self.heygen.upload_audio(audio_bytes)
            video_id = self.heygen.generate_video(audio_url)
            video_url = await self.heygen.wait_for_video(video_id)
            
            # Download video
            video_response = requests.get(video_url)
            video_filename = f"video_{post_id}.mp4"
            with open(video_filename, "wb") as f:
                f.write(video_response.content)
                
            # 6. Upload to YouTube
            await context.bot.send_message(chat_id=chat_id, text="🚀 Step 6: Uploading to YouTube")
            youtube_id = self.youtube.upload_video(video_filename, title, script)
            
            # Cleanup
            os.remove(video_filename)
            
            # 7. Final Notification
            youtube_link = f"https://www.youtube.com/watch?v={youtube_id}"
            await context.bot.send_message(chat_id=chat_id, text=f"✅ Video uploaded successfully!! Here is the link: {youtube_link}")

        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text=f"❌ An error occurred: {str(e)}")

# --- Bot Setup ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hi! Send me a Reddit link to turn it into an AI avatar video.')

def main():
    if not Config.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing in .env")
        return

    application = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    workflow = WorkflowManager()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, workflow.process_request))

    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
