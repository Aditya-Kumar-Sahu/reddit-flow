import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_youtube_connection():
    print("Testing YouTube Connection...")
    load_dotenv()
    
    secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE")
    if not secrets_file:
        print("❌ YOUTUBE_CLIENT_SECRETS_FILE not found in environment variables")
        return
        
    if not os.path.exists(secrets_file):
        print(f"❌ Secrets file not found at: {secrets_file}")
        return

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token_path = Path("token.json")
    
    try:
        creds = None
        if token_path.exists():
            print("Found existing token.json, trying to use it...")
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
            
        if not creds or not creds.valid:
            print("Token invalid or expired. You might need to run the main app to authenticate first, or this script will try to launch a browser.")
            # We can try to refresh if expired
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                print("Refreshing token...")
                creds.refresh(Request())
            else:
                print("❌ No valid token found. Please run the main application to perform initial authentication.")
                return

        service = build("youtube", "v3", credentials=creds)
        
        # Try a simple call, like listing channel info
        print("Fetching channel info...")
        request = service.channels().list(
            part="snippet,contentDetails,statistics",
            mine=True
        )
        response = request.execute()
        
        if "items" in response:
            channel = response["items"][0]
            print(f"✅ Successfully connected to channel: {channel['snippet']['title']}")
            print(f"   Subscribers: {channel['statistics']['subscriberCount']}")
        else:
            print("✅ Authenticated, but no channel found.")
            
    except Exception as e:
        print(f"❌ YouTube Connection Failed: {e}")

if __name__ == "__main__":
    test_youtube_connection()
