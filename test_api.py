import requests
import json

def test_api():
    base_url = "http://localhost:8000"
    
    try:
        # Test root endpoint
        print("Testing root endpoint...")
        response = requests.get(f"{base_url}/")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        print()
        
        # Test health endpoint
        print("Testing health endpoint...")
        response = requests.get(f"{base_url}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        print()
        
        # Test test endpoint
        print("Testing test endpoint...")
        response = requests.get(f"{base_url}/test")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        print()
        
        print("✅ API is working correctly!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API. Make sure the server is running.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_api() 