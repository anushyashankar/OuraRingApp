import random
from datetime import date, timedelta
from sqlalchemy.orm import sessionmaker
from app.core.database import sample_engine, Base
from app.models.metric import DailyMetric

# create session for sample db
SampleSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sample_engine)

# each metric has its own baseline so "normal for you" differs per metric
BASELINES = {
    "sleep_score": 84.0,
    "readiness_score": 78.0,
    "activity_score": 71.0,
}

def clamp(val, low=1.0, high=100.0):
    return max(low, min(high, val))

def generate_data():
    # test db file on clean session
    Base.metadata.drop_all(bind=sample_engine)
    Base.metadata.create_all(bind=sample_engine)
    db = SampleSessionLocal()

    end_date = date.today()
    start_date = end_date - timedelta(days=60)

    sick_start = end_date - timedelta(days=20)
    sick_end = end_date - timedelta(days=14)

    for i in range(61):
        current_day = start_date + timedelta(days=i)

        # scenario: sick between 20 and 14 days ago, then a gradual climb back
        # to baseline rather than a step change -- a real recovery has a ramp
        if sick_start <= current_day <= sick_end:
            day_of_illness = (current_day - sick_start).days
            # dips hardest mid-illness
            severity = 1.0 - abs(day_of_illness - 3) / 5.0
            drag = 30.0 * severity
        elif sick_end < current_day <= sick_end + timedelta(days=5):
            days_since = (current_day - sick_end).days
            drag = 18.0 * (1.0 - days_since / 6.0)
        else:
            drag = 0.0

        # sleep moves first; readiness follows it with a lag, activity is looser
        sleep = clamp(BASELINES["sleep_score"] - drag + random.uniform(-5, 5))
        readiness = clamp(
            BASELINES["readiness_score"] - drag * 0.9
            + (sleep - BASELINES["sleep_score"]) * 0.35
            + random.uniform(-6, 6)
        )
        activity = clamp(BASELINES["activity_score"] - drag * 0.7 + random.uniform(-11, 11))

        values = {
            "sleep_score": sleep,
            "readiness_score": readiness,
            "activity_score": activity,
        }

        # today reads unusually high, so the dashboard has a positive standout too
        if current_day == end_date:
            values["readiness_score"] = 96.0

        for metric, val in values.items():
            db.add(DailyMetric(day=current_day, metric=metric, value=round(val, 1)))

    db.commit()
    db.close()
    print(
        f"Generated 61 days of synthetic health data ({start_date} to {end_date}) "
        f"with a 'Sick Week' event from {sick_start} to {sick_end}."
    )

if __name__ == "__main__":
    generate_data()
