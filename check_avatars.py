import json
import os
import time
import requests
from dotenv import load_dotenv

TEMP_DIR = "temp"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

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
            # Handle if file is the direct API response structure or a simple list
            if isinstance(data, dict) and 'data' in data:
                avatars = data.get('data', {}).get('avatars', [])
            elif isinstance(data, list):
                avatars = data
            else:
                avatars = []
                
            if not avatars:
                print("⚠️  No avatars found in avatar.json. Check the file structure.")
                return
    except FileNotFoundError:
        print("❌ avatar.json not found")
        return
    except json.JSONDecodeError:
        print("❌ Failed to decode avatar.json")
        return

    available_avatars = []
    unavailable_avatars = []
    details = []

    print(f"Found {len(avatars)} avatars to check.\n")

    for i, avatar in enumerate(avatars):
        avatar_id = avatar.get('id')
        # Use a fallback name if one isn't in the list source
        source_name = avatar.get('avatar_name', f'Unknown_{i}')
        
        if not avatar_id:
            continue

        detail_url = f"https://api.heygen.com/v2/avatar/{avatar_id}/details"
        
        try:
            response = requests.get(detail_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                detail_data = response.json()
                data_obj = detail_data.get('data')

                # FIX: The details endpoint uses 'name', not 'avatar_name'
                if data_obj and 'name' in data_obj:
                    fetched_name = data_obj['name']
                    available_avatars.append(f"{fetched_name} ({avatar_id})")
                    details.append(data_obj)
                    print(f"✅ Available: {fetched_name}")
                else:
                    # If we get 200 OK but data is null, the ID might be deprecated or invalid
                    unavailable_avatars.append(f"{source_name} ({avatar_id}) - Data object empty")
                    print(f"⚠️  Unavailable (Empty Data): {source_name}")
            elif response.status_code == 429:
                print(f"⏳ Rate limited on {source_name}. Pausing for 5 seconds...")
                time.sleep(5)
                unavailable_avatars.append(f"{source_name} ({avatar_id}) - Rate Limited")
            else:
                unavailable_avatars.append(f"{source_name} ({avatar_id}) - Status {response.status_code}")
                print(f"❌ Unavailable ({response.status_code}): {source_name}")
                
        except Exception as e:
            unavailable_avatars.append(f"{source_name} ({avatar_id}) - Error: {str(e)}")
            print(f"❌ Error checking {source_name}: {e}")
        
        # Pause briefly between requests to be polite to the API
        time.sleep(0.5)

    print("\n" + "="*30)
    print("SUMMARY")
    print("="*30)
    
    print(f"\nAvailable Avatars ({len(available_avatars)}):")
    for name in available_avatars:
        print(f" - {name}")

    print(f"\nUnavailable Avatars ({len(unavailable_avatars)}):")
    for name in unavailable_avatars:
        print(f" - {name}")
        
    # print("\n" + "="*30)
    # print("Details of Available Avatars:")
    # print("="*30)
    # print("\nTotal Details Retrieved: ", len(details), end="\n\n")
    # for detail in details:
    #     print(json.dumps(detail, indent=2))

    with open(os.path.join(TEMP_DIR, "available_avatars_details.json"), "w") as f:
        json.dump(details, f, indent=2)
    print(f"\nDetails saved to {os.path.join(TEMP_DIR, 'available_avatars_details.json')}")

if __name__ == "__main__":
    check_avatar_availability()