import asyncio
import httpx
from app.services.oura import OuraService
from app.core.config import settings
from datetime import date, timedelta

async def test():
    service = OuraService(access_token=settings.OURA_ACCESS_TOKEN)
    end_date = date.today()
    start_date = end_date - timedelta(days=2)
    
    url = f"{service.base_url}/daily_sleep"
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=service.headers, params=params)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

if __name__ == "__main__":
    asyncio.run(test())
