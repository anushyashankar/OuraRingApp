import httpx
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.metric import DailyMetric

class OuraService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.ouraring.com/v2/usercollection"
        self.headers = {"Authorization": f"Bearer {self.access_token}"}

    async def sync_data(self, db: Session, days: int = 30):
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        collections = ["daily_sleep", "daily_readiness", "daily_activity"]

        total_synced = 0
        for collection in collections:
            data = await self._fetch_collection(collection, start_date, end_date)
            total_synced += self._process_collection(db, collection, data)

        # bundles all inserts at this point
        db.commit()
        return total_synced
        
    async def _fetch_collection(self, collection: str, start: date, end: date):
        url = f"{self.base_url}/{collection}"
        params = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat()
        }

        print(f"DEBUG: Syncing {collection} from {start} to {end}")

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])

            print(f"DEBUG: Found {len(data)} items for {collection}")
            return response.json().get("data", [])
        
    def _process_collection(self, db: Session, collection: str, data: list):
        count = 0
        from sqlalchemy import select
        
        for entry in data:
            day = date.fromisoformat(entry["day"])

            metrics_to_track = []
            if collection == "daily_sleep":
                metrics_to_track = [("sleep_score", entry.get("score"))]
            elif collection == "daily_readiness":
                metrics_to_track = [("readiness_score", entry.get("score"))]
            elif collection == "daily_activity":
                metrics_to_track = [("activity_score", entry.get("score"))]
            
            for metric_name, value in metrics_to_track:
                if value is not None:
                    # Check for existing record (Upsert logic)
                    stmt = select(DailyMetric).where(
                        DailyMetric.day == day,
                        DailyMetric.metric == metric_name
                    )
                    existing = db.execute(stmt).scalar_one_or_none()
                    
                    if existing:
                        existing.value = float(value)
                    else:
                        metric_record = DailyMetric(
                            day=day, metric=metric_name, value=float(value)
                        )
                        db.add(metric_record)
                        count += 1
            
        return count