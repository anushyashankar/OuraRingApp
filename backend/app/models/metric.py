from datetime import date, datetime
from sqlalchemy import String, Float, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    # primary key
    # Mapped[__]:  type hint
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    day: Mapped[date] = mapped_column(Date, index=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[float] = mapped_column(Float)

    # when row was added to db
    # autofills timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )