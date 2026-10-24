import os

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine
from app.models import SourceFetch, WindActual, WindForecast
from app.timeutils import parse_time


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch, request):
    if request.node.get_closest_marker("postgres"):
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL concurrency tests")
        if "_test" not in url.rsplit("/", 1)[-1]:
            pytest.fail("PostgreSQL tests require an explicitly named _test database")
    else:
        url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings.cache_clear()
    engine.cache_clear()
    Base.metadata.drop_all(engine())
    Base.metadata.create_all(engine())
    yield
    Base.metadata.drop_all(engine())
    engine().dispose()
    engine.cache_clear()
    settings.cache_clear()


@pytest.fixture
def session():
    with Session(engine()) as connection:
        yield connection


@pytest.fixture
def seed(session):
    fetch = SourceFetch(dataset="TEST", parameters={}, status="success")
    session.add(fetch)
    session.flush()

    def add(kind, target, published, value, received=None, conflicted=False):
        model = WindForecast if kind == "forecast" else WindActual
        record = model(
            start_time=parse_time(target),
            publish_time=parse_time(published),
            generation_mw=value,
            source_fetch_id=fetch.id,
            first_seen_at=parse_time(received or published),
            conflicted=conflicted,
        )
        session.add(record)
        session.commit()
        return record

    return add
