from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.timeutils import utcnow


class SourceFetch(Base):
    __tablename__ = "source_fetches"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(16))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(24))
    row_count: Mapped[int] = mapped_column(default=0)
    inserted_count: Mapped[int] = mapped_column(default=0)
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_response: Mapped[Any | None] = mapped_column(JSON(none_as_null=True))
    error: Mapped[str | None] = mapped_column(Text)


class WindForecast(Base):
    __tablename__ = "wind_forecasts"
    __table_args__ = (
        UniqueConstraint("start_time", "publish_time", name="uq_forecast_identity"),
        Index("ix_forecast_target_publish", "start_time", "publish_time"),
        Index("ix_forecast_received", "first_seen_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    publish_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation_mw: Mapped[float] = mapped_column(Float)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_fetch_id: Mapped[int] = mapped_column(ForeignKey("source_fetches.id"))
    conflicted: Mapped[bool] = mapped_column(Boolean, default=False)


class WindActual(Base):
    __tablename__ = "wind_actuals"
    __table_args__ = (
        UniqueConstraint("start_time", "publish_time", name="uq_actual_identity"),
        Index("ix_actual_target_publish", "start_time", "publish_time"),
        Index("ix_actual_received", "first_seen_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    publish_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation_mw: Mapped[float] = mapped_column(Float)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_fetch_id: Mapped[int] = mapped_column(ForeignKey("source_fetches.id"))
    conflicted: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncState(Base):
    __tablename__ = "sync_state"
    dataset: Mapped[str] = mapped_column(String(16), primary_key=True)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    active_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    method_version: Mapped[str] = mapped_column(String(30))
    parameters: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
