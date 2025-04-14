import asyncio
import time
from datetime import datetime

import aiohttp


async def generate_traffic(session, url, request_id):
    try:
        async with session.get(url, timeout=5) as response:
            await response.text()
            print(f"Request {request_id} completed successfully - Status: {response.status}")
    except Exception as e:
        print(f"Error in request {request_id}: {str(e)}")
        await asyncio.sleep(1)

async def main():

    service_url = "http://localhost:8080"
    concurrent_requests = 10
    
    print(f"Starting traffic generation at {datetime.now()}")
    print(f"Target URL: {service_url}")
    print(f"Concurrent requests: {concurrent_requests}")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                tasks = []
                for i in range(concurrent_requests):
                    task = generate_traffic(session, service_url, i)
                    tasks.append(task)
                
                await asyncio.gather(*tasks)
                print(f"\nCompleted batch of {concurrent_requests} requests")
                await asyncio.sleep(0.5)
            except KeyboardInterrupt:
                print("\nStopping traffic generation...")
                break
            except Exception as e:
                print(f"Batch error: {str(e)}")
                await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTraffic generation stopped by user")
