from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.services.oura import OuraService

router = APIRouter()

@router.post("/sync")
async def sync_oura_data(days: int = 30, db: Session = Depends(get_db)):
    # manual sync of oura data for days
    try:
        service = OuraService(access_token=settings.OURA_ACCESS_TOKEN)
        count = await service.sync_data(db, days=days)

        return {
            "status": "success",
            "message": f"Synced {count} metrics for last {days} days."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

