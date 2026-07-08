import random
from datetime import date, timedelta
from sqlalchemy.orm import sessionmaker
from app.core.database import sample_engine, Base
from app.models.metric import DailyMetric

# create session for sample db
SampleSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sample_engine)

def generate_data():
    # test db file on clean session
    Base.metadata.drop_all(bind=sample_engine)
    Base.metadata.create_all(bind=sample_engine)
    db = SampleSessionLocal()

    end_date = date.today()
    start_date = end_date - timedelta(days=60)
    metrics = ["sleep_score", "readiness_score", "activity_score"]

    for i in range(61):
        current_day = start_date + timedelta(days=i)

        # scenario: sick between 20 and 14 days ago
        is_sick = (end_date - timedelta(days=20)) <= current_day <= (end_date - timedelta(days=14))

        for metric in metrics:
            if is_sick:
                val = random.uniform(45, 55)
            else:
                val = random.uniform(78, 92)
            
            # big outlier
            if current_day == end_date and metric == "readiness_score":
                val = 98.0
            
            db.add(DailyMetric(day=current_day, metric=metric, value=round(val, 1)))

    db.commit()
    db.close()
    print("Generated 60 days of synthetic health data with a 'Sick Week' event.")

if __name__ == "__main__":
    generate_data()
