import subprocess
import sys
import os

def run_tests():
    tests = [
        "test_reddit.py",
        "test_gemini.py",
        "test_elevenlabs.py",
        "test_heygen.py",
        "test_youtube.py"
    ]
    
    print("🚀 Starting all service tests...\n")
    
    for test in tests:
        print(f"--- Running {test} ---")
        try:
            # Run the test script using the current python interpreter
            result = subprocess.run([sys.executable, test], cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print("Errors/Warnings:")
                print(result.stderr)
            
            if result.returncode != 0:
                print(f"⚠️ {test} exited with code {result.returncode}")
        except Exception as e:
            print(f"❌ Failed to run {test}: {e}")
        print("-" * 30 + "\n")

if __name__ == "__main__":
    run_tests()
