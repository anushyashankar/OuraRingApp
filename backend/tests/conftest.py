import os
import re
from datetime import date, timedelta
from types import SimpleNamespace

# point everything at throwaway values before any app module reads settings.
# env vars beat backend/.env, so the suite can never write to oura_app.db or
# spend a real Gemini request, even if a stub gets missed somewhere.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SAMPLE_DATABASE_URL"] = "sqlite://"
os.environ["OURA_ACCESS_TOKEN"] = "test-oura-token"
os.environ["GOOGLE_API_KEY"] = "test-google-key"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.metric import DailyMetric
from app.services import intelligence

# mirrors the banned list in the prompts in intelligence.py. text the app writes
# itself -- not the model -- has to meet the same bar it sets for the model.
BANNED_WORDS = [
    "z-score",
    "standard deviation",
    "sigma",
    "σ",
    "correlation",
    "coefficient",
    "baseline",
    "metric",
    "percentile",
    "statistically",
]


class FakeModel:
    """Stands in for Gemini. Records every prompt so tests can inspect them."""

    def __init__(self, text="Stub briefing.", error=None):
        self.text = text
        self.error = error
        self.prompts = []

    def generate_content(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


@pytest.fixture
def db():
    # StaticPool keeps a single in-memory connection, so FastAPI's worker threads
    # see the same database the test wrote to
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def add_series(db):
    """
    add_series("sleep_score", [70, 80, 90]) writes one value per day ending today,
    so the last value is today's. pass days_ago={0: 90, 7: 80} to leave gaps.
    """
    def _add(metric, values=None, days_ago=None):
        if values is not None:
            days_ago = {len(values) - 1 - i: v for i, v in enumerate(values)}
        today = date.today()
        for offset, value in days_ago.items():
            db.add(DailyMetric(
                day=today - timedelta(days=offset), metric=metric, value=float(value)
            ))
        db.commit()
    return _add


@pytest.fixture
def fake_model():
    return FakeModel()


@pytest.fixture
def service(fake_model):
    svc = intelligence.IntelligenceService()
    svc.model = fake_model
    return svc


@pytest.fixture
def assert_plain_language():
    def _check(text):
        lowered = text.lower()
        for word in BANNED_WORDS:
            assert word not in lowered, f"jargon {word!r} in user-facing text: {text!r}"
        assert not re.search(r"\d\.\d", text), f"decimal in user-facing text: {text!r}"
    return _check


@pytest.fixture(autouse=True)
def clear_briefing_cache():
    # the cache is module-level, so without this one test's briefing leaks into the next
    intelligence._BRIEFING_CACHE.clear()
    yield
    intelligence._BRIEFING_CACHE.clear()
