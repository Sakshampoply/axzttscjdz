from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return aware(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source timestamps must have a timezone")
    return parsed.astimezone(UTC)


def iso(value: datetime | None) -> str | None:
    return aware(value).isoformat().replace("+00:00", "Z") if value else None


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, time.min, LONDON).astimezone(UTC),
        datetime.combine(day + timedelta(days=1), time.min, LONDON).astimezone(UTC),
    )


def cutoff(day: date, clock: time) -> datetime:
    # Reject nonexistent/ambiguous local cutoffs instead of silently shifting a decision.
    local = datetime.combine(day, clock, LONDON)
    restored = local.astimezone(UTC).astimezone(LONDON)
    if restored.replace(tzinfo=None) != local.replace(tzinfo=None):
        raise ValueError("This London time does not exist on the clock-change day")
    if local.utcoffset() != local.replace(fold=1).utcoffset():
        raise ValueError("This London time is ambiguous; choose a time outside the repeated hour")
    return local.astimezone(UTC)


def historical_cutoff(day: date, clock: time) -> datetime:
    # A fixed daily policy uses the first repeated hour; gaps shift forward by the
    # clock change. The user-entered decision itself is still strictly validated.
    return datetime.combine(day, clock, LONDON).astimezone(UTC)


def slots(day: date, minutes: int = 60) -> list[datetime]:
    start, end = day_bounds(day)
    result = []
    while start < end:
        result.append(start)
        start += timedelta(minutes=minutes)
    return result
