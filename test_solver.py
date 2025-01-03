import asyncio
import aiohttp
import time

async def test_solver():
    url = "http://localhost:5000/solve"
    
    payload = {
        "url": "https://www.google.com/recaptcha/api2/demo",
        "sitekey": "6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
        "headless": True,
        "debug": False,
        "check_score": False
    }
    
    print(f"Sending request to solver at {url}")
    print(f"Testing with payload: {payload}")
    start_time = time.time()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=300) as response:  # 5 min timeout
                solve_time = time.time() - start_time
                result = await response.json()
                
                print(f"\nResponse status: {response.status}")
                
                if response.status == 200 and result.get("success"):
                    token = result["token"]
                    print(f"\nSuccess! Solved in {solve_time:.2f} seconds")
                    print(f"Token length: {len(token)}")
                    print(f"Token preview: {token[:50]}...")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"\nSolver failed: {error}")
                    print(f"Full response: {result}")
            
    except asyncio.TimeoutError:
        print("\nRequest timed out after 5 minutes")
    except aiohttp.ClientError:
        print("\nFailed to connect to solver API. Is the server running?")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_solver())
