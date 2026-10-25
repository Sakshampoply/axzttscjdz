import csv
import io
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.dashboard import dashboard_reports
from app.main import app
from app.models import SyncJob
from app.sync import ensure_dashboard_history
from app.timeutils import parse_time


def test_one_cutoff_selects_next_day_and_previous_thirty_decisions(session, seed):
    selected = seed("forecast", "2026-01-28T00:00Z", "2026-01-27T09:00Z", 100)
    seed("forecast", "2026-01-28T00:00Z", "2026-01-27T09:30Z", 5)
    seed("actual", "2026-01-28T00:00Z", "2026-01-28T00:30Z", 5)
    result = dashboard_reports(session, date(2026, 1, 27), time(9))
    forecast, evaluation = result["forecast"], result["evaluation"]
    assert forecast["delivery_date"] == "2026-01-28"
    assert forecast["points"][0]["forecast_id"] == selected.id
    assert "actual_mw" not in forecast["points"][0]
    assert evaluation["first_decision_date"] == "2025-12-28"
    assert evaluation["last_decision_date"] == "2026-01-26"
    assert evaluation["lookback_days"] == 30
    assert forecast["as_of"] == evaluation["as_of"] == result["selection"]["decision_at"]
    assert evaluation["metrics"]["expected"] == 29 * 24 + 9
    assert all(
        parse_time(p["start_time"]) + timedelta(minutes=30) <= parse_time(evaluation["as_of"])
        for p in evaluation["points"]
    )


def test_evaluation_uses_each_days_decision_forecast_and_no_later_actual(session, seed):
    original = seed("forecast", "2026-01-02T00:00Z", "2026-01-01T08:30Z", 100)
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T09:30Z", 80)
    actual = seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 80)
    seed("actual", "2026-01-02T00:00Z", "2026-01-03T00:00Z", 70)
    seed("forecast", "2026-01-02T01:00Z", "2026-01-01T08:30Z", 110)
    seed("actual", "2026-01-02T01:00Z", "2026-01-02T10:00Z", 20)
    result = dashboard_reports(session, date(2026, 1, 2), time(9))["evaluation"]
    point = next(p for p in result["points"] if p["start_time"] == "2026-01-02T00:00:00Z")
    assert point["forecast_id"] == original.id
    assert point["actual_id"] == actual.id
    assert result["metrics"]["matched"] == 1
    assert result["metrics"]["mae"] == 20
    assert result["metrics"]["bias"] == 20


def test_future_records_cannot_change_evaluation_or_its_native_cadence(session, seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 80)
    before = dashboard_reports(session, date(2026, 1, 2), time(9))["evaluation"]
    seed("forecast", "2026-01-02T00:30Z", "2026-01-03T07:30Z", 10)
    seed("actual", "2026-01-02T00:00Z", "2026-01-03T07:30Z", 10)
    after = dashboard_reports(session, date(2026, 1, 2), time(9))["evaluation"]
    assert before["fingerprint"] == after["fingerprint"]
    assert after["native_resolution_minutes"] == 60


def test_future_decisions_are_rejected_before_import_jobs(session):
    with TestClient(app) as client:
        assert client.get("/api/dashboard?decision_date=2099-01-01&decision_time=09:00").status_code == 422
        assert session.scalar(select(func.count(SyncJob.id))) == 0
        assert client.get("/api/dashboard?decision_date=2026-01-27").status_code == 422
        assert client.get("/api/dashboard?decision_date=2026-01-27&decision_time=09:00:01").status_code == 422


def test_empty_reports_and_clock_changes(session):
    result = dashboard_reports(session, date(2026, 1, 31), time(9))
    assert result["forecast"]["delivery_date"] == "2026-02-01"
    assert result["forecast"]["summary"]["average_mw"] is None
    assert result["evaluation"]["metrics"]["mae"] is None
    assert result["evaluation"]["metrics"]["matched"] == 0
    assert (
        dashboard_reports(session, date(2026, 10, 24), time(9))["forecast"]["summary"]["expected_count"] == 25
    )
    assert (
        dashboard_reports(session, date(2026, 3, 28), time(9))["forecast"]["summary"]["expected_count"] == 23
    )
    with pytest.raises(ValueError, match="ambiguous"):
        dashboard_reports(session, date(2026, 10, 25), time(1, 30))


def test_uncached_selection_coalesces_and_does_not_reimport_completed_days(session):
    first = ensure_dashboard_history(session, date(2026, 1, 27))
    session.commit()
    second = ensure_dashboard_history(session, date(2026, 1, 27))
    session.commit()
    assert first == second
    assert first["pending_days"] == 33
    assert session.scalar(select(func.count(SyncJob.id))) == 33
    jobs = session.scalars(select(SyncJob)).all()
    for job in jobs:
        job.status = "completed"
        job.active_key = None
    session.commit()
    assert ensure_dashboard_history(session, date(2026, 1, 27))["state"] == "ready"
    assert session.scalar(select(func.count(SyncJob.id))) == 33


def test_failed_import_is_reported_and_explicit_retry_reuses_queue(session):
    ensure_dashboard_history(session, date(2026, 1, 27))
    session.commit()
    jobs = session.scalars(select(SyncJob)).all()
    for job in jobs:
        job.status = "completed"
        job.active_key = None
    jobs[0].status = "failed"
    session.commit()
    status = ensure_dashboard_history(session, date(2026, 1, 27))
    assert status["state"] == "unavailable" and status["failed_days"] == 1
    assert ensure_dashboard_history(session, date(2026, 1, 27), retry_failed=True)["pending_days"] == 1
    session.commit()
    assert session.scalar(select(func.count(SyncJob.id))) == 34


@pytest.mark.parametrize("kind", ["forecast", "accuracy"])
def test_dashboard_export_is_cutoff_safe_frozen_and_matches_visible_values(seed, kind):
    seed("forecast", "2026-01-28T00:00Z", "2026-01-27T07:30Z", 110)
    seed("forecast", "2026-01-27T00:00Z", "2026-01-26T07:30Z", 100)
    seed("actual", "2026-01-27T00:00Z", "2026-01-27T00:30Z", 80)
    with TestClient(app) as client:
        report = client.get("/api/dashboard?decision_date=2026-01-27&decision_time=09:00").json()[
            "forecast" if kind == "forecast" else "evaluation"
        ]
        body = {
            "dashboard": True,
            "kind": kind,
            "parameters": {"decision_date": "2026-01-27", "decision_time": "09:00"},
            "expected_fingerprint": report["fingerprint"],
        }
        saved = client.post("/api/analysis-runs", json=body)
        assert saved.status_code == 201, saved.text
        run_id = saved.json()["id"]
        rows = list(csv.DictReader(io.StringIO(client.get(f"/api/export?run_id={run_id}").text)))
        assert len(rows) == len(report["points"])
        assert rows[0]["information_cutoff"] == report["as_of"]
        assert rows[0]["method_version"] == "decision-dashboard-v2"
        if kind == "forecast":
            assert "actual_mw" not in rows[0]
            assert float(rows[0]["forecast_mw"]) == 110
        else:
            matched = next(r for r in rows if r["actual_mw"])
            assert float(matched["error_mw"]) == 20
            assert all(parse_time(r["start_time"]) < parse_time(report["as_of"]) for r in rows)
        # Even newly received eligible source records cannot rewrite a saved assessment.
        seed("forecast", "2026-01-28T01:00Z", "2026-01-27T08:30Z", 90)
        assert client.get(f"/api/analysis-runs/{run_id}").json()["fingerprint"] == report["fingerprint"]
        if kind == "forecast":
            assert client.post("/api/analysis-runs", json=body).status_code == 409


@pytest.mark.parametrize(
    ("selected_day", "prior_target", "first_publication", "later_publication"),
    [
        (date(2026, 11, 1), "2026-10-26T00:00Z", "2026-10-25T00:20Z", "2026-10-25T01:10Z"),
        (date(2026, 4, 1), "2026-03-30T00:00Z", "2026-03-29T01:20Z", "2026-03-29T01:40Z"),
    ],
)
def test_valid_selection_can_evaluate_history_crossing_clock_changes(
    session, seed, monkeypatch, selected_day, prior_target, first_publication, later_publication
):
    monkeypatch.setattr("app.dashboard.utcnow", lambda: parse_time("2026-11-03T12:00Z"))
    monkeypatch.setattr("app.analytics.utcnow", lambda: parse_time("2026-11-03T12:00Z"))
    earlier = seed("forecast", prior_target, first_publication, 100)
    seed("forecast", prior_target, later_publication, 20)
    seed("actual", prior_target, prior_target, 80)
    result = dashboard_reports(session, selected_day, time(1, 30))["evaluation"]
    point = next(
        p
        for p in result["points"]
        if p["start_time"] == parse_time(prior_target).isoformat().replace("+00:00", "Z")
    )
    assert point["forecast_id"] == earlier.id
    assert result["metrics"]["mae"] == 20


def test_dashboard_snapshot_rejects_malformed_selection_and_fingerprint():
    with TestClient(app) as client:
        body = {
            "dashboard": True,
            "kind": "forecast",
            "parameters": {"decision_date": 42, "decision_time": "09:00"},
            "expected_fingerprint": "a" * 64,
        }
        assert client.post("/api/analysis-runs", json=body).status_code == 422
        body["expected_fingerprint"] = "not a fingerprint"
        assert client.post("/api/analysis-runs", json=body).status_code == 422
        assert client.get("/api/dashboard?decision_date=0001-01-01&decision_time=09:00").status_code == 422
