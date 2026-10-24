import math
from datetime import date, time

import pytest

from app.analytics import accuracy_analysis, forecast_analysis, metrics
from app.timeutils import cutoff, parse_time, slots


def test_metrics_match_hand_calculation():
    result = metrics([150, -50], [850, 1050], 24)
    assert result["mae"] == 100
    assert result["bias"] == 50
    assert result["rmse"] == pytest.approx(math.sqrt(12500))
    assert result["wape"] == pytest.approx(200 / 1900 * 100)
    assert result["coverage"] == pytest.approx(2 / 24 * 100)


def test_zero_generation_and_absent_evidence_are_not_perfect_accuracy():
    assert metrics([10], [0], 24)["wape"] is None
    assert metrics([], [], 24)["mae"] is None
    assert metrics([], [], 24)["coverage"] == 0


def test_latest_before_cutoff_not_latest_in_database(session, seed):
    first = seed("forecast", "2026-01-02T00:00Z", "2026-01-01T08:30Z", 1000)
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T09:30Z", 850)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 850)
    result = forecast_analysis(session, mode="replay", decision_date=date(2026, 1, 1), reveal_actuals=True)
    point = result["points"][0]
    assert point["forecast_id"] == first.id
    assert point["forecast_mw"] == 1000
    assert point["error_mw"] == 150


def test_forecast_exactly_at_cutoff_is_eligible(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T09:00Z", 100)
    assert (
        forecast_analysis(session, mode="replay", decision_date=date(2026, 1, 1))["points"][0]["forecast_mw"]
        == 100
    )


def test_actuals_hidden_in_decision_view(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T08:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 50)
    result = forecast_analysis(session, mode="replay", decision_date=date(2026, 1, 1))
    assert result["actual_curve"] == []
    assert result["points"][0]["actual_id"] is None
    assert result["metrics"]["matched"] == 0


def test_backfilled_record_is_not_originally_received(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T08:30Z", 100, received="2026-10-01T00:00Z")
    source = forecast_analysis(session, mode="replay", decision_date=date(2026, 1, 1))
    operational = forecast_analysis(
        session, mode="replay", decision_date=date(2026, 1, 1), availability="received"
    )
    assert source["summary"]["forecast_count"] == 1
    assert operational["summary"]["forecast_count"] == 0


def test_january_last_decision_uses_february_delivery(session, seed):
    seed("forecast", "2026-02-01T00:00Z", "2026-01-31T07:30Z", 100)
    seed("actual", "2026-02-01T00:00Z", "2026-02-01T00:30Z", 90)
    result = accuracy_analysis(session, start=date(2026, 1, 31), end=date(2026, 1, 31))
    assert result["points"][0]["delivery_date"] == "2026-02-01"
    assert result["metrics"]["mae"] == 10
    assert result["metrics"]["matched"] == 1


def test_half_hour_actual_is_not_an_extra_forecast(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 90)
    seed("actual", "2026-01-02T00:30Z", "2026-01-02T01:00Z", 5000)
    result = forecast_analysis(session, mode="replay", decision_date=date(2026, 1, 1), reveal_actuals=True)
    assert len(result["points"]) == 24
    assert len(result["actual_curve"]) == 2
    assert result["metrics"]["matched"] == 1
    assert result["metrics"]["mae"] == 10


def test_known_history_excludes_later_actual_publications(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-03T00:00Z", 90)
    result = accuracy_analysis(
        session,
        start=date(2026, 1, 1),
        end=date(2026, 1, 1),
        basis="known",
        known_at=parse_time("2026-01-02T09:00Z"),
    )
    assert result["metrics"]["matched"] == 0


def test_actual_revisions_respect_evaluation_snapshot(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 90)
    seed("actual", "2026-01-02T00:00Z", "2026-01-03T00:00Z", 80)
    result = accuracy_analysis(
        session, start=date(2026, 1, 1), end=date(2026, 1, 1), evaluation_at=parse_time("2026-01-02T12:00Z")
    )
    assert result["metrics"]["mae"] == 10


def test_conflicted_source_record_excluded(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100, conflicted=True)
    assert (
        forecast_analysis(session, mode="replay", decision_date=date(2026, 1, 1))["summary"]["forecast_count"]
        == 0
    )


def test_clock_change_slots_and_ambiguous_cutoffs():
    assert len(slots(date(2026, 3, 29), 30)) == 46
    assert len(slots(date(2026, 10, 25), 30)) == 50
    assert len(slots(date(2026, 10, 25))) == 25
    assert len(set(slots(date(2026, 10, 25)))) == 25
    with pytest.raises(ValueError, match="ambiguous"):
        cutoff(date(2026, 10, 25), time(1, 30))
    with pytest.raises(ValueError, match="does not exist"):
        cutoff(date(2026, 3, 29), time(1, 30))


def test_accuracy_range_is_bounded(session):
    with pytest.raises(ValueError, match="62"):
        accuracy_analysis(session, start=date(2026, 1, 1), end=date(2026, 5, 1))
