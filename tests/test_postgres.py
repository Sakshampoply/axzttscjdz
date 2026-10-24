import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.elexon import UpstreamError
from app.main import request_refresh
from app.models import SyncJob
from app.sync import claim_job, dataset_lock, enqueue

pytestmark = pytest.mark.postgres


def test_concurrent_refresh_is_one_postgres_job():
    def submit(_):
        with Session(engine()) as session:
            job = request_refresh(session)
            job_id = job.id
            session.commit()
            return job_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(submit, range(16)))
    assert len(set(ids)) == 1
    with Session(engine()) as session:
        assert session.scalar(select(func.count(SyncJob.id))) == 1


def test_workers_claim_different_jobs(session):
    for i in range(4):
        enqueue(session, "backfill", {"day": f"2026-01-0{i + 1}"}, key=f"backfill:{i}")
    session.commit()
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(claim_job, ["a", "b", "c", "d"]))
    assert len(set(ids)) == 4
    assert None not in ids


def test_dataset_lock_prevents_overlapping_fetches():
    acquired = threading.Event()
    release = threading.Event()

    def hold():
        with dataset_lock("WINDFOR"):
            acquired.set()
            release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        assert acquired.wait(5)
        try:
            with pytest.raises(UpstreamError, match="already"):
                with dataset_lock("WINDFOR"):
                    pass
        finally:
            release.set()
            future.result()
