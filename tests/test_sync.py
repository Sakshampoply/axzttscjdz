import hashlib
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.elexon import ElexonClient, UpstreamError
from app.models import SourceFetch, SyncJob, SyncState, WindActual, WindForecast
from app.sync import claim_job, enqueue, ingest, process_job
from app.timeutils import utcnow


def row(value=100, target="2026-01-02T00:00Z", published="2026-01-01T07:30Z"):
    return {"startTime": target, "publishTime": published, "generation": value}


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, _dataset, _params):
        return self.rows, hashlib.sha256(json.dumps(self.rows).encode()).hexdigest()


def test_import_is_idempotent_and_keeps_all_vintages(session):
    ingest("WINDFOR", {}, live=False, client=FakeClient([row()]))
    ingest("WINDFOR", {}, live=False, client=FakeClient([row()]))
    ingest("WINDFOR", {}, live=False, client=FakeClient([row(90, published="2026-01-01T09:30Z")]))
    assert session.scalar(select(func.count(WindForecast.id))) == 2
    assert (
        session.scalar(select(func.count(SourceFetch.id)).where(SourceFetch.raw_response.is_not(None))) >= 2
    )


def test_source_conflict_retains_original_and_flags_it(session):
    ingest("WINDFOR", {}, live=False, client=FakeClient([row(100)]))
    ingest("WINDFOR", {}, live=False, client=FakeClient([row(90)]))
    record = session.scalar(select(WindForecast))
    assert record.generation_mw == 100
    assert record.conflicted
    assert session.scalar(select(SourceFetch).order_by(SourceFetch.id.desc())).status == "conflict"


def test_invalid_payload_is_atomic_and_does_not_advance_watermark(session):
    with pytest.raises(UpstreamError):
        ingest("WINDFOR", {}, live=True, client=FakeClient([row(), row(None, target="2026-01-02T01:00Z")]))
    assert session.scalar(select(func.count(WindForecast.id))) == 0
    state = session.get(SyncState, "WINDFOR")
    assert state.watermark is None
    assert state.last_success_at is None
    assert state.last_error


def test_only_wind_actuals_are_retained(session):
    rows = [{**row(), "fuelType": "CCGT"}, {**row(90), "fuelType": "WIND"}]
    ingest("FUELHH", {}, live=False, client=FakeClient(rows))
    assert session.scalar(select(func.count(WindActual.id))) == 1
    assert session.scalar(select(WindActual.generation_mw)) == 90


def test_coalesced_jobs_share_identity(session):
    first = enqueue(session, "refresh")
    second = enqueue(session, "refresh")
    session.commit()
    assert first.id == second.id
    assert session.scalar(select(func.count(SyncJob.id))) == 1


def test_expired_job_is_reclaimed_but_active_lease_is_not(session):
    job = enqueue(session, "refresh")
    session.commit()
    assert claim_job("one") == job.id
    assert claim_job("two") is None
    session.refresh(job)
    job.lease_until = utcnow() - timedelta(seconds=1)
    session.commit()
    assert claim_job("two") == job.id
    session.refresh(job)
    assert job.lease_owner == "two"
    assert job.attempts == 2


def test_failed_job_respects_upstream_retry_after(session, monkeypatch):
    job = enqueue(session, "refresh")
    session.commit()
    job_id = claim_job("worker")

    def fail():
        raise UpstreamError("HTTP 429", 600)

    monkeypatch.setattr("app.sync.sync_latest", fail)
    before = utcnow()
    process_job(job_id, "worker")
    session.refresh(job)
    from app.timeutils import aware

    assert job.status == "pending"
    assert aware(job.available_at) >= before + timedelta(seconds=600)
    assert job.active_key == "refresh"


def test_http_retry_after_is_not_ignored(monkeypatch):
    import httpx

    response = httpx.Response(429, headers={"Retry-After": "720"})
    monkeypatch.setattr("app.elexon.httpx.get", lambda *a, **k: response)
    with pytest.raises(UpstreamError) as raised:
        ElexonClient().fetch("WINDFOR", {})
    assert raised.value.retry_seconds == 720


def test_connection_failure_keeps_previous_records_and_records_error(session):
    ingest("WINDFOR", {}, live=False, client=FakeClient([row()]))

    class BrokenClient:
        def fetch(self, *_args):
            raise UpstreamError("Connection timeout", 180)

    with pytest.raises(UpstreamError, match="timeout"):
        ingest("WINDFOR", {}, live=True, client=BrokenClient())
    assert session.scalar(select(func.count(WindForecast.id))) == 1
    state = session.get(SyncState, "WINDFOR")
    assert state.last_error == "Connection timeout"
    assert state.watermark is None
    assert session.scalar(select(SourceFetch).order_by(SourceFetch.id.desc())).status == "failed"


def test_stream_response_can_be_bare_array_or_envelope(monkeypatch):
    import httpx

    for payload in ([row()], {"data": [row()]}):
        monkeypatch.setattr(
            "app.elexon.httpx.get", lambda *a, payload=payload, **k: httpx.Response(200, json=payload)
        )
        records, _ = ElexonClient().fetch("WINDFOR", {})
        assert len(records) == 1
