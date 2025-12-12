import os
import sys
import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_heygen_connection():
    print("Testing HeyGen Connection...")
    load_dotenv()
    
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        print("❌ HEYGEN_API_KEY not found in environment variables")
        return

    try:
        url = "https://api.heygen.com/v2/avatars"
        headers = {
            "x-api-key": api_key,
            "accept": "application/json"
        }
        
        print("Fetching avatars list...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        avatars = data.get('data', {}).get('avatars', [])
        print(f"✅ Successfully connected. Found {len(avatars)} avatars.")
        if avatars:
            print(f"   First avatar: {avatars[0].get('avatar_name')} (ID: {avatars[0].get('avatar_id')})")
        
    except Exception as e:
        print(f"❌ HeyGen Connection Failed: {e}")

if __name__ == "__main__":
    test_heygen_connection()
