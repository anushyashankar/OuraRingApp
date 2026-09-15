import asyncio
from datetime import date, timedelta

from app.models.metric import DailyMetric


def brief(service, db):
    return asyncio.run(service.get_daily_briefing(db))


# ---- deterministic fallback -------------------------------------------------

def test_fallback_leads_with_what_stands_out(service, db, add_series, assert_plain_language):
    add_series("readiness_score", [70, 72, 74, 76, 70, 72, 74, 76, 99])
    add_series("sleep_score", [80, 82, 78, 80, 82, 78, 80, 82, 80])

    text = service._fallback_briefing(service.get_metric_analysis(db))

    assert text.startswith("Today stands out")
    assert "your readiness is unusually high for you" in text
    assert "your sleep is" not in text  # normal metrics aren't called out
    assert "Readiness came in at 99; your usual is around 76." in text
    assert_plain_language(text)


def test_fallback_mentions_mild_changes_when_nothing_stands_out(
    service, db, add_series, assert_plain_language
):
    add_series("readiness_score", [70, 80, 70, 80, 70, 80, 82])

    text = service._fallback_briefing(service.get_metric_analysis(db))

    assert text.startswith("Today looks close to a normal day, though")
    assert "your readiness is a little above your usual" in text
    assert_plain_language(text)


def test_fallback_says_normal_day_when_nothing_changed(service, db, add_series, assert_plain_language):
    add_series("sleep_score", [80, 82, 78, 80])

    text = service._fallback_briefing(service.get_metric_analysis(db))

    assert text.startswith("Today looks like a normal day for you")
    assert_plain_language(text)


# ---- daily briefing ---------------------------------------------------------

def test_no_data_explains_itself_without_calling_the_model(service, db, fake_model):
    result = brief(service, db)

    assert result["generated_by"] == "fallback"
    assert result["days_of_history"] == 0
    assert "Sync your Oura account" in result["briefing"]
    assert fake_model.prompts == []


def test_model_is_handed_the_computed_facts(service, db, add_series, fake_model):
    # the pitch claim: statistics are computed in python and given to the model as
    # facts. the model's job is wording, never deciding what counts as unusual.
    add_series("readiness_score", [70, 72, 74, 76, 70, 72, 74, 76, 99])

    result = brief(service, db)

    assert result == {"briefing": "Stub briefing.", "days_of_history": 9, "generated_by": "model"}
    prompt = fake_model.prompts[0]
    assert "Readiness (how recovered your body is): today 99, your usual is around 76." in prompt
    assert "This is unusually high for you." in prompt


def test_model_failure_falls_back_so_the_page_is_never_blank(service, db, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.error = Exception("429 quota exceeded")

    result = brief(service, db)

    assert result["generated_by"] == "fallback"
    assert result["briefing"].startswith("Today looks like a normal day")


def test_empty_model_response_falls_back(service, db, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.text = "   "

    assert brief(service, db)["generated_by"] == "fallback"


# ---- caching ----------------------------------------------------------------

def test_repeat_loads_reuse_the_briefing(service, db, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])

    first = brief(service, db)
    second = brief(service, db)

    assert first == second
    assert len(fake_model.prompts) == 1  # a reload must not spend a quota request


def test_fallbacks_are_not_cached(service, db, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])
    fake_model.error = Exception("temporarily unavailable")

    brief(service, db)
    brief(service, db)

    assert len(fake_model.prompts) == 2  # retried, not stuck on the fallback


def test_new_data_invalidates_the_briefing(service, db, add_series, fake_model):
    add_series("sleep_score", days_ago={1: 80, 2: 82, 3: 78})
    brief(service, db)

    add_series("sleep_score", days_ago={0: 60})
    brief(service, db)

    assert len(fake_model.prompts) == 2


def test_changed_spread_invalidates_the_briefing_even_with_the_same_average(
    service, db, add_series, fake_model
):
    # [74, 76, 80] and [60, 90, 80] share a latest value and an average, but not a
    # spread -- so today reads "a little above your usual" in one and "normal" in
    # the other. a stale briefing here would contradict the cards beneath it.
    add_series("readiness_score", [74, 76, 80])
    brief(service, db)
    assert "This is a little above your usual." in fake_model.prompts[0]

    today = date.today()
    for offset, value in {2: 60, 1: 90}.items():
        row = db.query(DailyMetric).filter_by(
            metric="readiness_score", day=today - timedelta(days=offset)
        ).one()
        row.value = float(value)
    db.commit()
    brief(service, db)

    assert len(fake_model.prompts) == 2
    assert "This is normal for you." in fake_model.prompts[1]
