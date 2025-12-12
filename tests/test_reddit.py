import os
import sys
import praw
from dotenv import load_dotenv

# Add parent directory to path to allow importing if needed, though we are using direct env vars here
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_reddit_connection():
    print("Testing Reddit Connection...")
    load_dotenv()
    
    try:
        reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT"),
            username=os.getenv("REDDIT_USERNAME"),
            password=os.getenv("REDDIT_PASSWORD")
        )
        
        user = reddit.user.me()
        print(f"✅ Successfully authenticated as: {user.name}")
        
        # Try to fetch a post to ensure read permissions
        print("Fetching a test post...")
        submission = reddit.submission(id="1nf7kh6") # Example post ID
        print(f"✅ Fetched post title: {submission.title}")
        
    except Exception as e:
        print(f"❌ Reddit Connection Failed: {e}")

if __name__ == "__main__":
    test_reddit_connection()
