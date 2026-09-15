import pytest

from app.services.intelligence import describe_level, describe_trend, friendly_metric_name


@pytest.mark.parametrize("z, label, tone", [
    (2.4, "unusually high for you", "high"),
    (1.5, "unusually high for you", "high"),  # thresholds are inclusive
    (1.49, "a little above your usual", "slightly-high"),
    (0.5, "a little above your usual", "slightly-high"),
    (0.49, "normal for you", "normal"),
    (0.0, "normal for you", "normal"),
    (-0.49, "normal for you", "normal"),
    (-0.5, "a little below your usual", "slightly-low"),
    (-1.49, "a little below your usual", "slightly-low"),
    (-1.5, "unusually low for you", "low"),
    (-3.0, "unusually low for you", "low"),
])
def test_describe_level_thresholds(z, label, tone):
    assert describe_level(z) == (label, tone)


@pytest.mark.parametrize("velocity, expected", [
    (None, None),  # no comparable point -- say nothing rather than guess
    (19.7, "up from last week"),
    (5, "up from last week"),
    (4.99, "about the same as last week"),
    (0, "about the same as last week"),
    (-4.99, "about the same as last week"),
    (-5, "down from last week"),
])
def test_describe_trend(velocity, expected):
    assert describe_trend(velocity) == expected


@pytest.mark.parametrize("metric, expected", [
    ("sleep_score", "Sleep"),
    ("readiness_score", "Readiness"),
    ("activity_score", "Activity"),
    ("resting_heart_rate", "Resting Heart Rate"),  # unknown metrics still read cleanly
])
def test_friendly_metric_name(metric, expected):
    assert friendly_metric_name(metric) == expected


def test_every_level_and_trend_label_is_plain_language(assert_plain_language):
    for z in [x / 10 for x in range(-40, 41)]:
        label, _ = describe_level(z)
        assert_plain_language(label)
    for velocity in [-20, -5, 0, 5, 20]:
        assert_plain_language(describe_trend(velocity))
