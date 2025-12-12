import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_gemini_connection():
    print("Testing Gemini Connection...")
    load_dotenv()
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ GOOGLE_API_KEY not found in environment variables")
        return

    try:
        genai.configure(api_key=api_key)
        
        # List available models to verify connection
        print("Listing available models...")
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"✅ Found {len(models)} models: {', '.join(models[:3])}...")
        
        # Try a simple generation
        model_name = 'gemini-2.5-flash' # Using a likely available model
        print(f"Testing generation with {model_name}...")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Say 'Hello, World!'")
        
        print(f"✅ Generation successful: {response.text.strip()}")
        
    except Exception as e:
        print(f"❌ Gemini Connection Failed: {e}")

if __name__ == "__main__":
    test_gemini_connection()
