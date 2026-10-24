import contextlib
import logging
import math
import time as time_module
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine
from app.elexon import ElexonClient, UpstreamError
from app.models import SourceFetch, SyncJob, SyncState, WindActual, WindForecast
from app.timeutils import aware, iso, parse_time, utcnow

log = logging.getLogger(__name__)
DATASETS = ("WINDFOR", "FUELHH")
LOCK_IDS = {"WINDFOR": 714001, "FUELHH": 714002, "queue": 714003}


@contextlib.contextmanager
def dataset_lock(dataset: str) -> Iterator[None]:
    # A session advisory lock survives short ORM transactions and covers the HTTP fetch.
    with engine().connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        if postgres:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_IDS[dataset]}
            )
            connection.commit()
            if not acquired:
                raise UpstreamError(f"{dataset} is already being synchronised", 5)
        try:
            yield
        finally:
            if postgres:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_IDS[dataset]})
                connection.commit()


def queue_lock(session: Session) -> None:
    if session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_IDS["queue"]})


def enqueue(session: Session, kind: str, payload: dict | None = None, key: str | None = None) -> SyncJob:
    queue_lock(session)
    active_key = key or kind
    existing = session.scalar(select(SyncJob).where(SyncJob.active_key == active_key))
    if existing:
        return existing
    job = SyncJob(kind=kind, payload=payload or {}, active_key=active_key)
    session.add(job)
    session.flush()
    return job


def enqueue_history(session: Session, start: date, end: date) -> int:
    if start > end:
        raise ValueError("Start date must be on or before end date")
    count = 0
    current = start
    while current <= end:
        enqueue(session, "backfill", {"day": current.isoformat()}, f"backfill:{current.isoformat()}")
        current += timedelta(days=1)
        count += 1
    return count


def ingest(dataset: str, parameters: dict, *, live: bool, client=None) -> dict:
    client = client or ElexonClient()
    model = WindForecast if dataset == "WINDFOR" else WindActual
    with dataset_lock(dataset):
        with Session(engine()) as session:
            state = session.get(SyncState, dataset)
            if state is None:
                state = SyncState(dataset=dataset)
                session.add(state)
            if state.retry_after and aware(state.retry_after) > utcnow():
                raise UpstreamError(
                    "Waiting for the upstream retry window",
                    (aware(state.retry_after) - utcnow()).total_seconds(),
                )
            if live:
                state.last_attempt_at = utcnow()
            session.commit()
        data = None
        checksum = None
        try:
            data, checksum = client.fetch(dataset, parameters)
            received_at = utcnow()
            # Validate every wind record before committing any observations or progress.
            clean = {}
            for row in data:
                if not isinstance(row, dict):
                    raise ValueError("Observation is not an object")
                if dataset == "FUELHH" and row.get("fuelType") != "WIND":
                    continue
                start = parse_time(row["startTime"])
                published = parse_time(row["publishTime"])
                value = row["generation"]
                if value is None or isinstance(value, bool):
                    raise ValueError("Generation is missing or invalid")
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError("Generation must be finite")
                if start.second or start.microsecond or start.minute not in {0, 30}:
                    raise ValueError("Unexpected target timestamp cadence")
                identity = (start, published)
                if identity in clean and clean[identity] != value:
                    raise ValueError("Conflicting observations inside one response")
                clean[identity] = value
            with Session(engine()) as session:
                # Identical payloads are retained once; checksums link subsequent successful checks.
                retained = session.scalar(
                    select(SourceFetch.id)
                    .where(SourceFetch.checksum == checksum, SourceFetch.raw_response.is_not(None))
                    .limit(1)
                )
                fetch = SourceFetch(
                    dataset=dataset,
                    parameters=parameters,
                    status="success",
                    row_count=len(clean),
                    checksum=checksum,
                    raw_response=None if retained else data,
                    fetched_at=received_at,
                )
                session.add(fetch)
                session.flush()
                inserted = conflicts = 0
                if clean:
                    start_min = min(x[0] for x in clean)
                    start_max = max(x[0] for x in clean)
                    rows = session.scalars(
                        select(model).where(model.start_time >= start_min, model.start_time <= start_max)
                    ).all()
                    existing = {(aware(r.start_time), aware(r.publish_time)): r for r in rows}
                    for (start, published), value in clean.items():
                        old = existing.get((start, published))
                        if old is not None:
                            if old.generation_mw != value:
                                old.conflicted = True
                                conflicts += 1
                            continue
                        session.add(
                            model(
                                start_time=start,
                                publish_time=published,
                                generation_mw=value,
                                first_seen_at=received_at,
                                source_fetch_id=fetch.id,
                            )
                        )
                        inserted += 1
                fetch.inserted_count = inserted
                if conflicts:
                    fetch.status = "conflict"
                    fetch.error = f"{conflicts} source identities changed value; originals retained and excluded from scoring"
                state = session.get(SyncState, dataset)
                if live:
                    # Bounded by the checked window: future-dated source timestamps must not skip data.
                    window_end = parse_time(parameters.get("publishDateTimeTo", iso(received_at)))
                    newest = min(max((x[1] for x in clean), default=window_end), window_end, received_at)
                    if state.watermark is None or newest > aware(state.watermark):
                        state.watermark = newest
                    # A historical catch-up chunk is not evidence that the latest window was checked.
                    if (received_at - window_end).total_seconds() < settings().stale_after_seconds:
                        state.last_success_at = received_at
                    state.last_error = fetch.error
                    state.retry_after = None
                session.commit()
                return {
                    "dataset": dataset,
                    "received": len(clean),
                    "inserted": inserted,
                    "conflicts": conflicts,
                }
        except Exception as exc:
            delay = exc.retry_seconds if isinstance(exc, UpstreamError) else 120
            with Session(engine()) as session:
                session.add(
                    SourceFetch(
                        dataset=dataset,
                        parameters=parameters,
                        status="failed",
                        error=str(exc),
                        raw_response=data,
                        checksum=checksum,
                    )
                )
                state = session.get(SyncState, dataset)
                if live:
                    state.last_error = str(exc)
                state.retry_after = utcnow() + timedelta(seconds=delay)
                session.commit()
            if isinstance(exc, UpstreamError):
                raise
            raise UpstreamError(f"Response validation failed: {exc}", delay) from exc


def sync_latest(client=None) -> None:
    failures = []
    for dataset in DATASETS:
        now = utcnow()
        with Session(engine()) as session:
            state = session.get(SyncState, dataset)
            since = (
                aware(state.watermark) - timedelta(hours=3)
                if state and state.watermark
                else now - timedelta(days=2)
            )
            if since < now - timedelta(days=2):
                enqueue_history(session, since.date(), (now - timedelta(days=2)).date())
                session.commit()
                since = now - timedelta(days=2)
        # Current data first; durable daily jobs recover longer outages without exceeding a job lease.
        while since < now:
            until = min(since + timedelta(days=1), now)
            try:
                ingest(
                    dataset,
                    {"publishDateTimeFrom": iso(since), "publishDateTimeTo": iso(until)},
                    live=True,
                    client=client,
                )
            except UpstreamError as exc:
                failures.append(exc)
                break
            since = until
    if failures:
        raise max(failures, key=lambda exc: exc.retry_seconds)


def backfill_day(day: date, client=None) -> None:
    start = datetime.combine(day, datetime.min.time(), UTC)
    end = start + timedelta(days=1)
    ingest(
        "WINDFOR",
        {"publishDateTimeFrom": iso(start), "publishDateTimeTo": iso(end)},
        live=False,
        client=client,
    )
    ingest(
        "FUELHH",
        {"settlementDateFrom": day.isoformat(), "settlementDateTo": day.isoformat()},
        live=False,
        client=client,
    )


def claim_job(owner: str) -> int | None:
    now = utcnow()
    with Session(engine()) as session:
        eligible = or_(
            and_(SyncJob.status == "pending", SyncJob.available_at <= now),
            and_(SyncJob.status == "running", SyncJob.lease_until < now),
        )
        job = session.scalar(
            select(SyncJob)
            .where(eligible)
            .order_by((SyncJob.kind == "refresh").desc(), SyncJob.created_at, SyncJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.started_at = now
        job.lease_owner = owner
        job.lease_until = now + timedelta(seconds=settings().job_lease_seconds)
        job.attempts += 1
        session.commit()
        return job.id


def process_job(job_id: int, owner: str) -> None:
    with Session(engine()) as session:
        job = session.get(SyncJob, job_id)
        if job.lease_owner != owner:
            return
        kind, payload = job.kind, job.payload
    error = None
    try:
        if kind == "refresh":
            sync_latest()
        elif kind == "backfill":
            backfill_day(date.fromisoformat(payload["day"]))
        else:
            raise ValueError(f"Unsupported job kind: {kind}")
    except Exception as exc:
        error = exc
        log.warning("Job %s failed: %s", job_id, exc)
    with Session(engine()) as session:
        job = session.get(SyncJob, job_id)
        if job.lease_owner != owner:
            return
        job.lease_owner = None
        job.lease_until = None
        if error is None:
            job.status = "completed"
            job.finished_at = utcnow()
            job.error = None
            job.active_key = None
        elif job.attempts >= 5:
            job.status = "failed"
            job.finished_at = utcnow()
            job.error = str(error)
            job.active_key = None
        else:
            job.status = "pending"
            job.error = str(error)
            delay = (
                error.retry_seconds if isinstance(error, UpstreamError) else min(120 * 2**job.attempts, 900)
            )
            job.available_at = utcnow() + timedelta(seconds=delay)
        session.commit()


def worker() -> None:
    owner = str(uuid.uuid4())
    with Session(engine()) as session:
        enqueue(session, "refresh")
        if (
            settings().bootstrap_demo
            and session.scalar(
                select(SyncJob.id)
                .where(SyncJob.kind == "backfill", SyncJob.payload["day"].as_string() == "2026-01-01")
                .limit(1)
            )
            is None
        ):
            enqueue_history(session, date(2025, 12, 30), date(2026, 2, 1))
        # Bootstrap runs once per database; persisted daily jobs survive worker restarts.
        if session.scalar(select(SyncJob.id).where(SyncJob.kind == "backfill").limit(1)) is None:
            today = utcnow().date()
            enqueue_history(session, today - timedelta(days=settings().bootstrap_history_days + 2), today)
        session.commit()
    next_tick = 0.0
    next_reconcile = 0.0
    log.info("Synchronisation worker started: %s", owner)
    while True:
        tick = time_module.monotonic()
        if tick >= next_tick:
            with Session(engine()) as session:
                enqueue(session, "refresh")
                if tick >= next_reconcile:
                    # Daily reconciliation catches revised actuals and late historical records.
                    today = utcnow().date()
                    enqueue_history(session, today - timedelta(days=32), today)
                    next_reconcile = tick + 86400
                session.commit()
            next_tick = tick + settings().sync_interval_seconds
        job_id = claim_job(owner)
        if job_id:
            process_job(job_id, owner)
        else:
            time_module.sleep(2)
