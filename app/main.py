import csv
import hmac
import io
import logging
import uuid
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics import METHOD_VERSION, accuracy_analysis, forecast_analysis
from app.config import settings
from app.dashboard import dashboard_reports, decision_cutoff, source_freshness
from app.db import engine, get_session
from app.models import AnalysisRun, SyncJob, SyncState, WindActual, WindForecast
from app.sync import enqueue, ensure_dashboard_history, queue_lock, run_bounded_jobs
from app.timeutils import aware, iso, utcnow

log = logging.getLogger(__name__)
app = FastAPI(
    title="GridBricks Wind Intelligence",
    version="1.0.0",
    description="Decision-time GB wind forecast analysis",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings().allowed_origins.split(",") if x.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def invalid_input(_request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def request_refresh(session: Session, *, cooldown=True) -> SyncJob:
    queue_lock(session)
    active = session.scalar(select(SyncJob).where(SyncJob.active_key == "refresh"))
    if active:
        return active
    last = session.scalar(
        select(SyncJob).where(SyncJob.kind == "refresh").order_by(SyncJob.created_at.desc()).limit(1)
    )
    if (
        cooldown
        and last
        and (utcnow() - aware(last.created_at)).total_seconds() < settings().refresh_cooldown_seconds
    ):
        return last
    return enqueue(session, "refresh")


def schedule_runner(background_tasks: BackgroundTasks):
    if settings().request_driven_sync:
        background_tasks.add_task(run_bounded_jobs)


def refresh_if_stale(background_tasks: BackgroundTasks):
    with Session(engine()) as session:
        states = session.scalars(select(SyncState)).all()
        stale = len(states) < 2 or any(
            s.last_success_at is None
            or (utcnow() - aware(s.last_success_at)).total_seconds() > settings().stale_after_seconds
            for s in states
        )
        if stale:
            request_refresh(session)
            session.commit()
    schedule_runner(background_tasks)


@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "service": "gridbricks", "method_version": METHOD_VERSION}


@app.get("/api/forecast")
def forecast(
    background_tasks: BackgroundTasks,
    mode: Literal["current", "replay"] = "current",
    decision_date: date | None = None,
    decision_time: time = time(9),
    availability: Literal["published", "received"] = "published",
    reveal_actuals: bool = False,
    compare_publication: datetime | None = None,
    as_of: datetime | None = None,
    evaluation_at: datetime | None = None,
    session: Session = Depends(get_session),
):
    refresh_if_stale(background_tasks)
    return forecast_analysis(
        session,
        mode=mode,
        decision_date=decision_date,
        decision_time=decision_time,
        availability=availability,
        reveal_actuals=reveal_actuals,
        compare_publication=compare_publication,
        as_of=as_of,
        evaluation_at=evaluation_at,
    )


@app.get("/api/dashboard")
def dashboard(
    background_tasks: BackgroundTasks,
    decision_date: date,
    decision_time: time,
    session: Session = Depends(get_session),
):
    result = dashboard_reports(session, decision_date, decision_time)
    result["source"] = source_freshness(session)
    result["history"] = ensure_dashboard_history(session, decision_date)
    session.commit()
    refresh_if_stale(background_tasks)
    return result


@app.get("/api/forecast-history")
def forecast_history(
    decision_date: date,
    decision_time: time = time(9),
    availability: Literal["published", "received"] = "published",
    session: Session = Depends(get_session),
):
    result = forecast_analysis(
        session,
        mode="replay",
        decision_date=decision_date,
        decision_time=decision_time,
        availability=availability,
    )
    return {
        "as_of": result["as_of"],
        "publications": result["publications"],
        "alignment": result["alignment"],
    }


@app.get("/api/accuracy")
def accuracy(
    background_tasks: BackgroundTasks,
    start: date,
    end: date,
    decision_time: time = time(9),
    basis: Literal["known", "retrospective"] = "retrospective",
    known_at: datetime | None = None,
    availability: Literal["published", "received"] = "published",
    evaluation_at: datetime | None = None,
    session: Session = Depends(get_session),
):
    refresh_if_stale(background_tasks)
    return accuracy_analysis(
        session,
        start=start,
        end=end,
        decision_time=decision_time,
        basis=basis,
        known_at=known_at,
        availability=availability,
        evaluation_at=evaluation_at,
    )


@app.get("/api/data-quality")
def data_quality(session: Session = Depends(get_session)):
    now = utcnow()
    states = {s.dataset: s for s in session.scalars(select(SyncState))}
    datasets = []
    for name, model in (("WINDFOR", WindForecast), ("FUELHH", WindActual)):
        state = states.get(name)
        count, earliest, latest, publication = session.execute(
            select(
                func.count(model.id),
                func.min(model.start_time),
                func.max(model.start_time),
                func.max(model.publish_time),
            )
        ).one()
        lag = (
            (now - aware(state.last_success_at)).total_seconds() if state and state.last_success_at else None
        )
        datasets.append(
            {
                "dataset": name,
                "records": count,
                "first_target": iso(earliest),
                "latest_target": iso(latest),
                "latest_publication": iso(publication),
                "last_checked": iso(state.last_success_at) if state else None,
                "last_attempt": iso(state.last_attempt_at) if state else None,
                "stale": lag is None or lag > settings().stale_after_seconds,
                "error": state.last_error if state else None,
                "retry_after": iso(state.retry_after) if state else None,
            }
        )
    jobs = session.scalars(
        select(SyncJob)
        .where(SyncJob.status.in_(["pending", "running"]))
        .order_by((SyncJob.kind == "refresh").desc(), SyncJob.created_at)
        .limit(10)
    ).all()
    failures = session.scalar(select(func.count(SyncJob.id)).where(SyncJob.status == "failed"))
    return {
        "checked_at": iso(now),
        "timezone": "Europe/London",
        "datasets": datasets,
        "jobs": [job_dict(j) for j in jobs],
        "failed_jobs": failures,
        "sync_interval_seconds": settings().sync_interval_seconds,
        "sync_mode": "scheduled_requests" if settings().request_driven_sync else "worker",
        "scope": "GB operational wind: WINDFOR and FUELHH WIND only",
    }


def job_dict(job):
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "created_at": iso(job.created_at),
        "available_at": iso(job.available_at),
        "error": job.error,
    }


@app.post("/api/refresh", status_code=202)
def refresh(
    background_tasks: BackgroundTasks,
    decision_date: date | None = None,
    decision_time: time | None = None,
    session: Session = Depends(get_session),
):
    if (decision_date is None) != (decision_time is None):
        raise HTTPException(422, "Provide both a decision date and time")
    if decision_date is not None:
        decision_cutoff(decision_date, decision_time)
    job = request_refresh(session)
    if decision_date is not None and job.status in {"pending", "running"}:
        ensure_dashboard_history(session, decision_date, retry_failed=True)
    result = job_dict(job)
    session.commit()
    schedule_runner(background_tasks)
    return result


@app.get("/api/jobs/{job_id}")
def job_status(job_id: int, session: Session = Depends(get_session)):
    job = session.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job_dict(job)


class SnapshotRequest(BaseModel):
    kind: Literal["forecast", "accuracy"]
    parameters: dict
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dashboard: bool = False


@app.post("/api/analysis-runs", status_code=201)
def snapshot(body: SnapshotRequest, session: Session = Depends(get_session)):
    from app.timeutils import parse_time

    p = dict(body.parameters)
    if body.dashboard:
        if set(p) != {"decision_date", "decision_time"}:
            raise HTTPException(422, "A dashboard export requires its decision date and time")
        try:
            selected_date = date.fromisoformat(p["decision_date"])
            selected_time = time.fromisoformat(p["decision_time"])
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "Provide a valid decision date and time") from exc
        reports = dashboard_reports(session, selected_date, selected_time)
        result = reports["forecast" if body.kind == "forecast" else "evaluation"]
        return save_snapshot(session, body, result)
    # Explicit allowlists prevent a client from submitting arbitrary server-side calls.
    allowed = (
        {
            "mode",
            "decision_date",
            "decision_time",
            "availability",
            "reveal_actuals",
            "compare_publication",
            "as_of",
            "evaluation_at",
        }
        if body.kind == "forecast"
        else {"start", "end", "decision_time", "basis", "known_at", "availability", "evaluation_at"}
    )
    if set(p) - allowed:
        raise HTTPException(422, "Unsupported snapshot parameter")
    for key in ("decision_date", "start", "end"):
        if p.get(key):
            p[key] = date.fromisoformat(p[key])
    if p.get("decision_time"):
        p["decision_time"] = time.fromisoformat(p["decision_time"])
    for key in ("compare_publication", "as_of", "known_at", "evaluation_at"):
        if p.get(key):
            p[key] = parse_time(p[key])
    if p.get("availability", "published") not in {"published", "received"}:
        raise HTTPException(422, "Invalid availability mode")
    if p.get("mode", "current") not in {"current", "replay"} or p.get("basis", "retrospective") not in {
        "known",
        "retrospective",
    }:
        raise HTTPException(422, "Invalid analysis mode")
    try:
        result = (
            forecast_analysis(session, **p) if body.kind == "forecast" else accuracy_analysis(session, **p)
        )
    except TypeError as exc:
        raise HTTPException(422, "Missing or invalid snapshot parameters") from exc
    return save_snapshot(session, body, result)


def save_snapshot(session: Session, body: SnapshotRequest, result: dict):
    if not hmac.compare_digest(result["fingerprint"], body.expected_fingerprint):
        raise HTTPException(409, "Source evidence changed. Refresh the analysis before exporting.")
    existing = session.scalar(select(AnalysisRun).where(AnalysisRun.fingerprint == result["fingerprint"]))
    if existing:
        return {"id": existing.id, "fingerprint": existing.fingerprint}
    record = AnalysisRun(
        id=str(uuid.uuid4()),
        fingerprint=result["fingerprint"],
        parameters=body.parameters,
        method_version=result["method_version"],
        result=result,
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        record = session.scalar(select(AnalysisRun).where(AnalysisRun.fingerprint == result["fingerprint"]))
    return {"id": record.id, "fingerprint": record.fingerprint}


@app.get("/api/analysis-runs/{run_id}")
def read_snapshot(run_id: str, session: Session = Depends(get_session)):
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(404, "Analysis snapshot not found")
    return {"id": run.id, "created_at": iso(run.created_at), **run.result}


@app.get("/api/export")
def export(run_id: str, format: Literal["csv", "json"] = "csv", session: Session = Depends(get_session)):
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(404, "Analysis snapshot not found")
    if format == "json":
        return JSONResponse(
            {"id": run.id, "created_at": iso(run.created_at), **run.result},
            headers={"Content-Disposition": f'attachment; filename="gridbricks-{run.id}.json"'},
        )
    output = io.StringIO(newline="")
    points = run.result["points"]
    keys = list(points[0]) if points else ["start_time", "forecast_mw", "actual_mw", "error_mw"]
    metadata_keys = [
        "analysis_id",
        "method_version",
        "information_cutoff",
        "evaluation_at",
        "availability",
        "alignment",
    ]
    metric_metadata = {}
    if "bias_percent" in run.result.get("metrics", {}):
        metric_metadata = {
            "window_wape_percent": run.result["metrics"]["wape"],
            "window_bias_percent": run.result["metrics"]["bias_percent"],
            "window_below_forecast_percent": run.result["metrics"]["below_forecast_percent"],
            "window_p90_absolute_error_mw": run.result["metrics"]["p90_absolute_error_mw"],
        }
    writer = csv.DictWriter(output, fieldnames=metadata_keys + list(metric_metadata) + keys)
    writer.writeheader()
    for row in points:
        writer.writerow(
            {
                "analysis_id": run.id,
                "method_version": run.method_version,
                "information_cutoff": run.result.get("as_of")
                or run.result.get("known_at")
                or "per-day decision cutoff",
                "evaluation_at": run.result.get("evaluation_at"),
                "availability": run.result["availability"],
                "alignment": run.result["alignment"],
                **metric_metadata,
                **row,
            }
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="gridbricks-{run.result["kind"]}-{run.id[:8]}.csv"'
        },
    )


static_dir = Path(settings().frontend_dist)
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
