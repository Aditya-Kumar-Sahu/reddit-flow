import os
import sys
import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_elevenlabs_connection():
    print("Testing ElevenLabs Connection...")
    load_dotenv()
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("❌ ELEVENLABS_API_KEY not found in environment variables")
        return

    try:
        url = "https://api.elevenlabs.io/v1/user"
        headers = {
            "xi-api-key": api_key
        }
        
        print("Fetching user info...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        subscription = data.get('subscription', {})
        print(f"✅ Successfully connected as: {data.get('first_name', 'Unknown')}")
        print(f"   Character count: {subscription.get('character_count', 0)} / {subscription.get('character_limit', 0)}")
        
    except Exception as e:
        print(f"❌ ElevenLabs Connection Failed: {e}")

if __name__ == "__main__":
    test_elevenlabs_connection()
