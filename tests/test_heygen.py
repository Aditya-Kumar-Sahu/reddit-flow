import os
import sys
import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_heygen_connection():
    print("Testing HeyGen Connection...")
    load_dotenv()
    
    api_key = os.getenv("HEYGEN_API_KEY")
    avatar_id = os.getenv("HEYGEN_AVATAR_ID")

    assert api_key, "❌ HEYGEN_API_KEY not found in environment variables"

    headers = {
        "x-api-key": api_key,
        "accept": "application/json"
    }

    try:
        # Test Specific Avatar ID
        if avatar_id:
            print(f"\nTesting specific avatar ID: {avatar_id}")
            detail_url = f"https://api.heygen.com/v2/avatar/{avatar_id}/details"
            
            print("Fetching avatar details...")
            detail_response = requests.get(detail_url, headers=headers, timeout=30)
            detail_response.raise_for_status()
            
            detail_data = detail_response.json()
            avatar_name = detail_data.get('data', {}).get('avatar_name', 'Unknown')
            assert avatar_name != 'Unknown', "Failed to retrieve valid avatar name"
            print(f"✅ Successfully fetched details for avatar: {avatar_name}")
            print(f"Avatar Details: {detail_data}")
        else:
            print("\n⚠️ HEYGEN_AVATAR_ID not found in environment variables. Skipping specific avatar test.")
        
    except Exception as e:
        raise AssertionError(f"❌ HeyGen Connection Failed: {e}")


if __name__ == "__main__":
    test_heygen_connection()
