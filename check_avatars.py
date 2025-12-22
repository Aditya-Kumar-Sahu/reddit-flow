import json
import os
import requests
from dotenv import load_dotenv

def check_avatar_availability():
    print("Checking Avatar Availability...")
    load_dotenv()
    
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        print("❌ HEYGEN_API_KEY not found in environment variables")
        return

    headers = {
        "x-api-key": api_key,
        "accept": "application/json"
    }

    # Load avatar IDs from avatar.json
    try:
        with open('avatar.json', 'r') as f:
            data = json.load(f)
            avatars = data.get('data', {}).get('avatars', [])
    except FileNotFoundError:
        print("❌ avatar.json not found")
        return
    except json.JSONDecodeError:
        print("❌ Failed to decode avatar.json")
        return

    available_avatars = []
    unavailable_avatars = []

    print(f"Found {len(avatars)} avatars to check.\n")

    for avatar in avatars:
        avatar_id = avatar.get('avatar_id')
        avatar_name = avatar.get('avatar_name', 'Unknown Name')
        
        if not avatar_id:
            continue

        detail_url = f"https://api.heygen.com/v2/avatar/{avatar_id}/details"
        
        try:
            response = requests.get(detail_url, headers=headers, timeout=10)
            if response.status_code == 200:
                detail_data = response.json()
                # Check if we got valid data back. 
                # The API might return 200 but with an error in the body or empty data if not found/accessible?
                # Based on docs, 200 OK means success.
                # Let's assume if we get a name back it's good.
                fetched_name = detail_data.get('data', {}).get('avatar_name')
                if fetched_name:
                    available_avatars.append(f"{fetched_name} ({avatar_id})")
                    print(f"✅ Available: {avatar_name}")
                else:
                    unavailable_avatars.append(f"{avatar_name} ({avatar_id}) - No data returned")
                    print(f"⚠️  Unavailable (No Data): {avatar_name}")
            else:
                unavailable_avatars.append(f"{avatar_name} ({avatar_id}) - Status {response.status_code}")
                print(f"❌ Unavailable ({response.status_code}): {avatar_name}")
                
        except Exception as e:
            unavailable_avatars.append(f"{avatar_name} ({avatar_id}) - Error: {str(e)}")
            print(f"❌ Error checking {avatar_name}: {e}")

    print("\n" + "="*30)
    print("SUMMARY")
    print("="*30)
    
    print(f"\nAvailable Avatars ({len(available_avatars)}):")
    for name in available_avatars:
        print(f" - {name}")

    print(f"\nUnavailable Avatars ({len(unavailable_avatars)}):")
    for name in unavailable_avatars:
        print(f" - {name}")

if __name__ == "__main__":
    check_avatar_availability()
