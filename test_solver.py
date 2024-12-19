import requests
import time

def test_solver():
    url = "http://localhost:8080/solve"
    
    payload = {
        "site_key": "6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
        "url": "https://www.google.com/recaptcha/api2/demo"
    }
    
    print(f"Sending request to solver at {url}")
    print(f"Testing with payload: {payload}")
    start_time = time.time()
    
    try:
        response = requests.post(url, json=payload, timeout=300)  # 5 min timeout
        solve_time = time.time() - start_time
        
        print(f"\nResponse status: {response.status_code}")
        result = response.json()
        
        if response.status_code == 200 and "token" in result:
            token = result["token"]
            print(f"\nSuccess! Solved in {solve_time:.2f} seconds")
            print(f"Token length: {len(token)}")
            print(f"Token preview: {token[:50]}...")
        else:
            error = result.get('error', 'Unknown error')
            print(f"\nSolver failed: {error}")
            print(f"Full response: {result}")
            
    except requests.exceptions.Timeout:
        print("\nRequest timed out after 5 minutes")
    except requests.exceptions.ConnectionError:
        print("\nFailed to connect to solver API. Is the server running?")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")

if __name__ == "__main__":
    test_solver()
