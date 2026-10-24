import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WindActual, WindForecast
from app.timeutils import LONDON, aware, cutoff, day_bounds, iso, slots, utcnow

METHOD_VERSION = "native-target-v1"
ALIGNMENT = (
    "Exact startTime match: hourly WINDFOR targets versus the FUELHH half-hour beginning at that timestamp."
)


def metrics(errors: list[float], actuals: list[float], expected: int) -> dict:
    values = np.asarray(errors, dtype=float)
    denominator = float(np.abs(actuals).sum())
    return {
        "mae": float(np.abs(values).mean()) if len(values) else None,
        "rmse": float(np.sqrt(np.square(values).mean())) if len(values) else None,
        "bias": float(values.mean()) if len(values) else None,
        "wape": float(np.abs(values).sum() / denominator * 100) if len(values) and denominator else None,
        "matched": len(errors),
        "expected": expected,
        "coverage": len(errors) / expected * 100 if expected else None,
    }


def eligible(row, at: datetime, availability: str) -> bool:
    return (
        not row.conflicted
        and aware(row.publish_time) <= at
        and (availability == "published" or aware(row.first_seen_at) <= at)
    )


def group_records(rows) -> dict:
    grouped = defaultdict(list)
    for row in rows:
        grouped[aware(row.start_time)].append(row)
    for values in grouped.values():
        values.sort(key=lambda r: aware(r.publish_time))
    return grouped


def infer_cadence(grouped: dict) -> int:
    targets = sorted(grouped)
    # The scoped source supports hourly targets; retain genuine half-hour targets if supplied.
    if any(t.minute == 30 for t in targets):
        return 30
    return 60


def series(session: Session, model, start: datetime, end: datetime):
    return session.scalars(
        select(model)
        .where(model.start_time >= start, model.start_time < end)
        .order_by(model.start_time, model.publish_time)
    ).all()


def stamp_result(result: dict) -> dict:
    result["method_version"] = METHOD_VERSION
    result["alignment"] = ALIGNMENT
    # Exclude freshness clocks from this evidence fingerprint; selected records and cutoffs remain included.
    result["fingerprint"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def forecast_analysis(
    session: Session,
    *,
    mode="current",
    decision_date: date | None = None,
    decision_time: time = time(9),
    availability="published",
    reveal_actuals=False,
    compare_publication: datetime | None = None,
    as_of: datetime | None = None,
    evaluation_at: datetime | None = None,
) -> dict:
    now = utcnow()
    if mode == "current":
        selected_at = aware(as_of) if as_of else now
        decision_date = selected_at.astimezone(LONDON).date()
    else:
        decision_date = decision_date or now.astimezone(LONDON).date()
        selected_at = cutoff(decision_date, decision_time)
    if selected_at > now:
        raise ValueError("The selected decision time is in the future")
    evaluation = aware(evaluation_at) if evaluation_at else now
    if evaluation > now:
        raise ValueError("The evaluation time is in the future")
    if compare_publication and aware(compare_publication) > selected_at:
        raise ValueError("The comparison publication must be before the decision cutoff")
    delivery = decision_date + timedelta(days=1)
    start, end = day_bounds(delivery)
    forecasts = group_records(series(session, WindForecast, start, end))
    actuals = group_records(series(session, WindActual, start, end))
    cadence = infer_cadence(
        {
            target: values
            for target, values in forecasts.items()
            if any(eligible(r, selected_at, availability) for r in values)
        }
    )
    expected_slots = slots(delivery, cadence)
    points, publications = [], set()
    selected_rows, previous_rows = [], []
    actual_cutoff = evaluation if reveal_actuals else selected_at
    actual_curve = []
    for target, versions in sorted(actuals.items()):
        candidates = [r for r in versions if eligible(r, actual_cutoff, availability)]
        if candidates and target + timedelta(minutes=30) <= actual_cutoff:
            row = candidates[-1]
            actual_curve.append(
                {
                    "start_time": iso(target),
                    "generation_mw": row.generation_mw,
                    "publish_time": iso(row.publish_time),
                    "observation_id": row.id,
                }
            )
    for target in expected_slots:
        versions = [r for r in forecasts.get(target, []) if eligible(r, selected_at, availability)]
        publications.update(iso(r.publish_time) for r in versions)
        selected = versions[-1] if versions else None
        previous = (
            next((r for r in reversed(versions) if aware(r.publish_time) <= aware(compare_publication)), None)
            if compare_publication
            else (versions[-2] if len(versions) > 1 else None)
        )
        available_actuals = [r for r in actuals.get(target, []) if eligible(r, actual_cutoff, availability)]
        actual = (
            available_actuals[-1]
            if available_actuals and target + timedelta(minutes=30) <= actual_cutoff
            else None
        )
        if selected:
            selected_rows.append(selected)
        if previous:
            previous_rows.append(previous)
        points.append(
            {
                "start_time": iso(target),
                "local_time": target.astimezone(LONDON).strftime("%H:%M %Z"),
                "forecast_mw": selected.generation_mw if selected else None,
                "forecast_publish_time": iso(selected.publish_time) if selected else None,
                "forecast_first_seen_at": iso(selected.first_seen_at) if selected else None,
                "forecast_id": selected.id if selected else None,
                "previous_mw": previous.generation_mw if previous else None,
                "previous_publish_time": iso(previous.publish_time) if previous else None,
                "previous_id": previous.id if previous else None,
                "revision_mw": selected.generation_mw - previous.generation_mw
                if selected and previous
                else None,
                "actual_mw": actual.generation_mw if actual else None,
                "actual_publish_time": iso(actual.publish_time) if actual else None,
                "actual_id": actual.id if actual else None,
                "error_mw": selected.generation_mw - actual.generation_mw if selected and actual else None,
                "status": "missing_forecast"
                if selected is None
                else ("evaluated" if actual else "awaiting_actual" if reveal_actuals else "actuals_hidden"),
            }
        )
    valid = [p for p in points if p["forecast_mw"] is not None]
    paired = [p for p in points if p["error_mw"] is not None]
    minimum = min(valid, key=lambda p: p["forecast_mw"]) if valid else None
    maximum = max(valid, key=lambda p: p["forecast_mw"]) if valid else None
    revised = [p for p in valid if p["revision_mw"] is not None]
    downward = min(revised, key=lambda p: p["revision_mw"]) if revised else None
    if downward and downward["revision_mw"] >= 0:
        downward = None
    ramps = []
    for left, right in zip(points, points[1:], strict=False):
        if left["forecast_mw"] is not None and right["forecast_mw"] is not None:
            ramps.append(
                {
                    "from": left["local_time"],
                    "to": right["local_time"],
                    "mw_per_hour": (right["forecast_mw"] - left["forecast_mw"]) / (cadence / 60),
                }
            )
    decline = min(ramps, key=lambda r: r["mw_per_hour"]) if ramps else None
    insights = []
    if minimum:
        insights.append(
            {
                "kind": "low",
                "title": "Lowest expected wind",
                "text": f"{minimum['forecast_mw']:,.0f} MW at {minimum['local_time']}. Review this period alongside demand and contracts in your own systems.",
            }
        )
    if downward:
        insights.append(
            {
                "kind": "revision",
                "title": "A downward revision to review",
                "text": f"Expected wind at {downward['local_time']} fell by {abs(downward['revision_mw']):,.0f} MW versus the comparison forecast.",
            }
        )
    if decline and decline["mw_per_hour"] < 0:
        insights.append(
            {
                "kind": "ramp",
                "title": "Largest forecast decline",
                "text": f"Output falls at {abs(decline['mw_per_hour']):,.0f} MW per hour between {decline['from']} and {decline['to']}.",
            }
        )
    missing = len(expected_slots) - len(valid)
    if missing:
        insights.append(
            {
                "kind": "quality",
                "title": "Incomplete forecast coverage",
                "text": f"{missing} of {len(expected_slots)} native targets have no eligible forecast. Missing values are not zero.",
            }
        )
    return stamp_result(
        {
            "kind": "forecast",
            "mode": mode,
            "decision_date": decision_date.isoformat(),
            "delivery_date": delivery.isoformat(),
            "decision_time": decision_time.strftime("%H:%M"),
            "as_of": iso(selected_at),
            "evaluation_at": iso(evaluation),
            "availability": availability,
            "reveal_actuals": reveal_actuals,
            "compare_publication": iso(compare_publication),
            "native_resolution_minutes": cadence,
            "points": points,
            "actual_curve": actual_curve,
            "publications": sorted(publications, reverse=True),
            "summary": {
                "minimum": minimum,
                "maximum": maximum,
                "largest_downward_revision": downward,
                "largest_decline": decline,
                "forecast_count": len(valid),
                "expected_count": len(expected_slots),
                "forecast_coverage": len(valid) / len(expected_slots) * 100,
                "latest_publication": iso(max((r.publish_time for r in selected_rows), default=None)),
                "oldest_publication": iso(min((r.publish_time for r in selected_rows), default=None)),
                "average_mw": float(np.mean([p["forecast_mw"] for p in valid])) if valid else None,
            },
            "metrics": metrics(
                [p["error_mw"] for p in paired], [p["actual_mw"] for p in paired], len(points)
            ),
            "insights": insights,
        }
    )


def accuracy_analysis(
    session: Session,
    *,
    start: date,
    end: date,
    decision_time: time = time(9),
    basis="retrospective",
    known_at: datetime | None = None,
    availability="published",
    evaluation_at: datetime | None = None,
) -> dict:
    if end < start or (end - start).days > 61:
        raise ValueError("Choose an ordered range of at most 62 decision days")
    now = utcnow()
    evaluation = (
        aware(known_at) if basis == "known" and known_at else aware(evaluation_at) if evaluation_at else now
    )
    if basis == "known" and known_at is None:
        raise ValueError("Known-before-decision analysis requires its information cutoff")
    if evaluation > now:
        raise ValueError("The information cutoff is in the future")
    first, _ = day_bounds(start + timedelta(days=1))
    _, last = day_bounds(end + timedelta(days=1))
    forecasts = group_records(series(session, WindForecast, first, last))
    actuals = group_records(series(session, WindActual, first, last))
    cadence = infer_cadence(forecasts)
    rows, daily = [], []
    current = start
    while current <= end:
        selected_at = cutoff(current, decision_time)
        delivery = current + timedelta(days=1)
        targets = slots(delivery, cadence)
        day_rows = []
        for target in targets:
            f = (
                [r for r in forecasts.get(target, []) if eligible(r, selected_at, availability)]
                if selected_at <= evaluation
                else []
            )
            a = [r for r in actuals.get(target, []) if eligible(r, evaluation, availability)]
            forecast, actual = f[-1] if f else None, a[-1] if a else None
            # An actual must refer to a completed period, even if an upstream timestamp is malformed.
            if target + timedelta(minutes=30) > evaluation:
                actual = None
            row = {
                "decision_date": current.isoformat(),
                "delivery_date": delivery.isoformat(),
                "start_time": iso(target),
                "local_time": target.astimezone(LONDON).strftime("%H:%M %Z"),
                "forecast_mw": forecast.generation_mw if forecast else None,
                "actual_mw": actual.generation_mw if actual else None,
                "forecast_id": forecast.id if forecast else None,
                "actual_id": actual.id if actual else None,
                "forecast_publish_time": iso(forecast.publish_time) if forecast else None,
                "actual_publish_time": iso(actual.publish_time) if actual else None,
                "error_mw": forecast.generation_mw - actual.generation_mw if forecast and actual else None,
            }
            rows.append(row)
            day_rows.append(row)
        scored = [r for r in day_rows if r["error_mw"] is not None]
        daily.append(
            {
                "decision_date": current.isoformat(),
                "delivery_date": delivery.isoformat(),
                **metrics([r["error_mw"] for r in scored], [r["actual_mw"] for r in scored], len(targets)),
            }
        )
        current += timedelta(days=1)
    scored = [r for r in rows if r["error_mw"] is not None]
    errors = [r["error_mw"] for r in scored]
    histogram = []
    if errors:
        spread = max(float(np.max(np.abs(errors))), 1)
        counts, edges = np.histogram(errors, bins=np.linspace(-spread, spread, 10))
        histogram = [
            {"from_mw": float(edges[i]), "to_mw": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(len(counts))
        ]
    # pandas groups real source observations, never interpolated values.
    hourly = []
    if scored:
        frame = pd.DataFrame(scored)
        for hour, group in frame.groupby("local_time", sort=True):
            hourly.append(
                {"local_time": hour, "mae": float(group.error_mw.abs().mean()), "count": len(group)}
            )
    overall = metrics(errors, [r["actual_mw"] for r in scored], len(rows))
    worst = max((d for d in daily if d["mae"] is not None), key=lambda d: d["mae"], default=None)
    insights = []
    if errors:
        insights.append(
            {
                "title": "Typical forecast miss",
                "text": f"Across {len(errors):,} matched targets, the average absolute miss was {overall['mae']:,.0f} MW. This is historical evidence, not a guaranteed future range.",
            }
        )
        tendency = "below" if overall["bias"] > 0 else "above" if overall["bias"] < 0 else "equal to"
        insights.append(
            {
                "title": "Forecast tendency",
                "text": f"Actual wind averaged {abs(overall['bias']):,.0f} MW {tendency} the decision-time forecast.",
            }
        )
    else:
        insights.append(
            {
                "title": "No matched evidence yet",
                "text": "There is insufficient eligible history for this range and information cutoff. Later outcomes are not used to fill the gap.",
            }
        )
    return stamp_result(
        {
            "kind": "accuracy",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "decision_time": decision_time.strftime("%H:%M"),
            "basis": basis,
            "known_at": iso(known_at),
            "evaluation_at": iso(evaluation),
            "availability": availability,
            "native_resolution_minutes": cadence,
            "metrics": overall,
            "daily": daily,
            "points": rows,
            "histogram": histogram,
            "hourly": hourly,
            "worst_day": worst,
            "represented_days": sum(d["matched"] > 0 for d in daily),
            "insights": insights,
        }
    )
