import statistics
from datetime import date

import pytest

from app.services.intelligence import describe_level, describe_trend


def stats_by_metric(service, db):
    return {s["metric"]: s for s in service.get_metric_analysis(db)}


def correlation_between(service, db, metric_a, metric_b):
    for c in service.get_correlations_json(db):
        if {c["metric_a"], c["metric_b"]} == {metric_a, metric_b}:
            return c
    return None


# ---- per-metric statistics --------------------------------------------------

def test_no_data_returns_empty(service, db):
    assert service.get_metric_analysis(db) == []


def test_mean_stdev_and_z_score_come_from_her_own_history(service, db, add_series):
    values = [70, 72, 74, 76, 78, 96]
    add_series("readiness_score", values)

    s = stats_by_metric(service, db)["readiness_score"]
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)

    assert s["latest_value"] == 96
    assert s["mean"] == pytest.approx(mean)
    assert s["stdev"] == pytest.approx(stdev)
    assert s["z_score"] == pytest.approx((96 - mean) / stdev)
    assert s["days_of_history"] == 6


def test_plain_language_fields_agree_with_the_numbers(service, db, add_series):
    add_series("sleep_score", [80, 82, 78, 81, 79, 83, 80, 84, 88])
    add_series("readiness_score", [75, 70, 78, 72, 74, 76, 71, 73, 50])
    add_series("activity_score", [65, 70, 72, 68, 71, 69, 70, 67, 70])

    for s in service.get_metric_analysis(db):
        assert (s["level_label"], s["level_tone"]) == describe_level(s["z_score"])
        assert s["comparison"] == f"Your usual is around {round(s['mean'])}"
        assert s["trend_label"] == describe_trend(s["velocity"])


def test_latest_is_the_most_recent_day_not_the_last_inserted(service, db, add_series):
    add_series("sleep_score", days_ago={0: 88})
    add_series("sleep_score", days_ago={5: 70, 3: 75})

    s = stats_by_metric(service, db)["sleep_score"]
    assert s["latest_value"] == 88
    assert s["latest_day"] == date.today()


def test_metric_with_a_single_point_is_skipped(service, db, add_series):
    add_series("sleep_score", [80])
    add_series("readiness_score", [70, 75])

    assert set(stats_by_metric(service, db)) == {"readiness_score"}


def test_constant_values_do_not_divide_by_zero(service, db, add_series):
    add_series("sleep_score", [80, 80, 80, 80])

    s = stats_by_metric(service, db)["sleep_score"]
    assert s["z_score"] == 0
    assert s["level_tone"] == "normal"


def test_points_older_than_the_window_are_excluded(service, db, add_series):
    add_series("sleep_score", days_ago={0: 80, 1: 80, 61: 10})

    s = stats_by_metric(service, db)["sleep_score"]
    assert s["days_of_history"] == 2
    assert s["mean"] == 80


# ---- 7-day velocity ---------------------------------------------------------

@pytest.mark.parametrize("gap, expected", [
    (6, None),     # too recent to call a week
    (7, 10.0),
    (8, 10.0),
    (9, 10.0),
    (10, None),    # too old to call a week
])
def test_velocity_only_uses_a_point_seven_to_nine_days_back(service, db, add_series, gap, expected):
    add_series("sleep_score", days_ago={0: 90, gap: 80})

    assert stats_by_metric(service, db)["sleep_score"]["velocity"] == expected


def test_velocity_prefers_the_point_closest_to_a_week(service, db, add_series):
    add_series("sleep_score", days_ago={0: 90, 7: 80, 9: 60})

    assert stats_by_metric(service, db)["sleep_score"]["velocity"] == 10


def test_velocity_does_not_fall_back_to_the_oldest_point(service, db, add_series):
    # regression: this used to reach back to the oldest point in the 60-day window
    # and still report the difference as a weekly change
    add_series("sleep_score", days_ago={0: 90, 1: 88, 2: 89, 40: 50})

    s = stats_by_metric(service, db)["sleep_score"]
    assert s["velocity"] is None
    assert s["trend_label"] is None


# ---- correlations -----------------------------------------------------------

def test_series_that_rise_together_correlate_at_one(service, db, add_series):
    add_series("sleep_score", [60, 70, 80, 90, 100])
    add_series("readiness_score", [50, 60, 70, 80, 90])

    assert correlation_between(service, db, "sleep_score", "readiness_score")["r"] == 1.0


def test_opposite_series_correlate_at_minus_one(service, db, add_series):
    add_series("sleep_score", [60, 70, 80, 90, 100])
    add_series("activity_score", [100, 90, 80, 70, 60])

    assert correlation_between(service, db, "sleep_score", "activity_score")["r"] == -1.0


def test_pairs_with_fewer_than_five_shared_days_are_skipped(service, db, add_series):
    add_series("sleep_score", [60, 70, 80, 90])
    add_series("readiness_score", [50, 60, 70, 80])

    assert service.get_correlations_json(db) == []


def test_only_days_where_both_metrics_exist_are_paired(service, db, add_series):
    # the unmatched outliers would wreck r if the series were misaligned
    add_series("sleep_score", days_ago={0: 100, 1: 90, 2: 80, 3: 70, 4: 60, 10: 0})
    add_series("readiness_score", days_ago={0: 90, 1: 80, 2: 70, 3: 60, 4: 50, 11: 1000})

    assert correlation_between(service, db, "sleep_score", "readiness_score")["r"] == 1.0


def test_constant_series_has_no_correlation(service, db, add_series):
    add_series("sleep_score", [80, 80, 80, 80, 80])
    add_series("readiness_score", [50, 60, 70, 80, 90])

    c = correlation_between(service, db, "sleep_score", "readiness_score")
    assert c["r"] == 0.0
    assert c["interpretation"] == "Your sleep and how recovered you feel have moved fairly independently."


@pytest.mark.parametrize("sleep, readiness, activity", [
    ([60, 70, 80, 90, 100], [50, 60, 70, 80, 90], [40, 50, 60, 70, 80]),   # all rise together
    ([60, 70, 80, 90, 100], [90, 80, 70, 60, 50], [40, 50, 60, 70, 80]),   # mixed directions
    ([80, 80, 80, 80, 80], [50, 60, 70, 80, 90], [90, 70, 80, 60, 75]),    # flat pairs
])
def test_correlation_interpretations_are_plain_language(
    service, db, add_series, assert_plain_language, sleep, readiness, activity
):
    add_series("sleep_score", sleep)
    add_series("readiness_score", readiness)
    add_series("activity_score", activity)

    correlations = service.get_correlations_json(db)
    assert len(correlations) == 3
    for c in correlations:
        assert_plain_language(c["interpretation"])
