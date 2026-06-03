import asyncio
from app.services.oura import OuraService
from app.core.config import settings
from app.core.database import SessionLocal

async def main():
    db = SessionLocal()
    service = OuraService(access_token=settings.OURA_ACCESS_TOKEN)
    count = await service.sync_data(db, days=100)
    print(f"Synced {count} metrics.")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
