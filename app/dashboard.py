"""One decision moment, a next-day forecast, and earlier information only."""

from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import accuracy_analysis, forecast_analysis, stamp_result
from app.config import settings
from app.models import SyncState
from app.timeutils import aware, cutoff, day_bounds, iso, utcnow

DASHBOARD_METHOD = "decision-dashboard-v2"
LOOKBACK_DAYS = 30


def decision_cutoff(day: date, clock: time):
    if day < date.min + timedelta(days=32):
        raise ValueError("The decision date is too early to evaluate the preceding 30 days")
    if clock.tzinfo is not None or clock.second or clock.microsecond:
        raise ValueError("Choose a London decision time in whole minutes")
    selected = cutoff(day, clock)
    if selected > utcnow():
        raise ValueError("Choose a decision date and time that is not in the future")
    return selected


def dashboard_reports(session: Session, decision_date: date, decision_time: time) -> dict:
    selected = decision_cutoff(decision_date, decision_time)
    selection = {
        "decision_date": decision_date.isoformat(),
        "decision_time": decision_time.strftime("%H:%M"),
        "decision_at": iso(selected),
    }
    common = {
        **selection,
        "as_of": iso(selected),
        "evaluation_at": iso(selected),
        "availability": "published",
    }
    raw_forecast = forecast_analysis(
        session,
        mode="replay",
        decision_date=decision_date,
        decision_time=decision_time,
        evaluation_at=selected,
    )
    forecast_fields = (
        "start_time",
        "local_time",
        "forecast_mw",
        "forecast_publish_time",
        "forecast_id",
    )
    forecast_points = [{key: p[key] for key in forecast_fields} for p in raw_forecast["points"]]
    valid = [p for p in forecast_points if p["forecast_mw"] is not None]
    forecast = stamp_result(
        {
            **common,
            "kind": "forecast",
            "delivery_date": raw_forecast["delivery_date"],
            "native_resolution_minutes": raw_forecast["native_resolution_minutes"],
            "points": forecast_points,
            "summary": {
                "average_mw": raw_forecast["summary"]["average_mw"],
                "minimum": min(valid, key=lambda p: p["forecast_mw"]) if valid else None,
                "maximum": max(valid, key=lambda p: p["forecast_mw"]) if valid else None,
                "forecast_count": len(valid),
                "expected_count": len(forecast_points),
                "coverage": raw_forecast["summary"]["forecast_coverage"],
                "latest_publication": raw_forecast["summary"]["latest_publication"],
            },
        },
        DASHBOARD_METHOD,
    )
    first_decision = decision_date - timedelta(days=LOOKBACK_DAYS)
    last_decision = decision_date - timedelta(days=1)
    raw_evaluation = accuracy_analysis(
        session,
        start=first_decision,
        end=last_decision,
        decision_time=decision_time,
        basis="known",
        known_at=selected,
        completed_only=True,
    )
    evaluation = stamp_result(
        {
            **common,
            "kind": "accuracy",
            "window_start": iso(day_bounds(first_decision + timedelta(days=1))[0]),
            "window_end": iso(selected),
            "first_decision_date": first_decision.isoformat(),
            "last_decision_date": last_decision.isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "native_resolution_minutes": raw_evaluation["native_resolution_minutes"],
            "metrics": raw_evaluation["metrics"],
            "points": raw_evaluation["points"],
            "latest_publication": max(
                (p["forecast_publish_time"] for p in raw_evaluation["points"] if p["forecast_publish_time"]),
                default=None,
            ),
        },
        DASHBOARD_METHOD,
    )
    return {"selection": selection, "forecast": forecast, "evaluation": evaluation}


def source_freshness(session: Session) -> dict:
    states = session.scalars(select(SyncState).where(SyncState.dataset.in_(["WINDFOR", "FUELHH"]))).all()
    checked = [aware(s.last_success_at) for s in states if s.last_success_at]
    last_checked = min(checked) if len(checked) == 2 else None
    return {
        "last_checked": iso(last_checked),
        "stale": last_checked is None
        or (utcnow() - last_checked).total_seconds() > settings().stale_after_seconds,
        "source_issue": any(s.last_error for s in states),
    }
