import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import database
from app.main import app
from app.services import intelligence


@pytest.fixture
def client(db, fake_model, monkeypatch):
    def override_db():
        yield db

    app.dependency_overrides[database.get_db] = override_db
    # routes build their own IntelligenceService, so swap the model at the source
    monkeypatch.setattr(intelligence.genai, "GenerativeModel", lambda *args, **kwargs: fake_model)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_summary_returns_plain_language_fields(client, add_series):
    add_series("readiness_score", [70, 72, 74, 76, 70, 72, 74, 76, 99])

    response = client.get("/api/v1/metrics/summary")

    assert response.status_code == 200
    [readiness] = response.json()
    assert readiness["friendly_name"] == "Readiness"
    assert readiness["level_label"] == "unusually high for you"
    assert readiness["comparison"] == "Your usual is around 76"


def test_briefing_still_answers_when_the_model_is_down(client, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.error = Exception("429 quota exceeded")

    response = client.get("/api/v1/briefing")

    assert response.status_code == 200
    assert response.json()["generated_by"] == "fallback"


def test_chat_forwards_history_to_the_model(client, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.text = "Because your sleep dropped."

    response = client.post("/api/v1/chat", json={
        "question": "why?",
        "history": [
            {"sender": "user", "text": "Was I unwell recently?"},
            {"sender": "ai", "text": "Yes, in late July."},
        ],
    })

    assert response.status_code == 200
    assert response.json() == {"answer": "Because your sleep dropped."}
    assert "User: Was I unwell recently?" in fake_model.prompts[0]


def test_chat_works_without_history(client, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])

    response = client.post("/api/v1/chat", json={"question": "How did I sleep?"})

    assert response.status_code == 200
    assert "first question" in fake_model.prompts[0]


def test_chat_rejects_malformed_history(client):
    response = client.post("/api/v1/chat", json={
        "question": "why?",
        "history": [{"sender": "user"}],  # no text
    })

    assert response.status_code == 422


def test_chat_maps_quota_errors_to_429(client, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.error = Exception("429 You exceeded your current quota")

    response = client.post("/api/v1/chat", json={"question": "How did I sleep?"})

    assert response.status_code == 429
    assert response.json()["detail"] == "Daily question limit reached. Try again tomorrow."


def test_chat_reports_other_failures_as_500(client, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.error = Exception("connection reset")

    response = client.post("/api/v1/chat", json={"question": "How did I sleep?"})

    assert response.status_code == 500


# ---- demo data isolation ----------------------------------------------------

def _session_for(headers):
    request = Request({"type": "http", "headers": headers})
    sessions = database.get_db(request)
    session = next(sessions)
    return session, sessions


def test_sample_header_routes_to_the_sample_database():
    session, sessions = _session_for([(b"x-use-sample", b"true")])
    try:
        assert session.get_bind() is database.sample_engine
    finally:
        sessions.close()


def test_requests_default_to_the_real_database():
    session, sessions = _session_for([])
    try:
        assert session.get_bind() is database.engine
    finally:
        sessions.close()
