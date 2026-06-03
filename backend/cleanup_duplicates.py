from app.core.database import SessionLocal
from app.models.metric import DailyMetric
from sqlalchemy import select, func

def cleanup():
    db = SessionLocal()
    
    # Find duplicates: same day and metric
    subquery = (
        select(DailyMetric.day, DailyMetric.metric, func.min(DailyMetric.id).label("min_id"))
        .group_by(DailyMetric.day, DailyMetric.metric)
        .subquery()
    )
    
    # Delete everything that is NOT the min_id for that day/metric pair
    stmt = (
        select(DailyMetric.id)
        .outerjoin(subquery, DailyMetric.id == subquery.c.min_id)
        .where(subquery.c.min_id == None)
    )
    
    ids_to_delete = db.execute(stmt).scalars().all()
    
    if ids_to_delete:
        print(f"Deleting {len(ids_to_delete)} duplicate records...")
        from sqlalchemy import delete
        db.execute(delete(DailyMetric).where(DailyMetric.id.in_(ids_to_delete)))
        db.commit()
        print("Cleanup complete.")
    else:
        print("No duplicates found.")
    
    db.close()

if __name__ == "__main__":
    cleanup()
