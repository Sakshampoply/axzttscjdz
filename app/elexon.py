import hashlib
import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.config import settings


class UpstreamError(Exception):
    def __init__(self, message: str, retry_seconds: float = 120):
        super().__init__(message)
        self.retry_seconds = max(1, retry_seconds)


class ElexonClient:
    def fetch(self, dataset: str, parameters: dict) -> tuple[list, str]:
        if dataset not in {"WINDFOR", "FUELHH"}:
            raise ValueError("Only the two scoped wind datasets are supported")
        params = dict(parameters)
        if dataset == "FUELHH":
            params["fuelType"] = "WIND"
        try:
            response = httpx.get(
                f"{settings().elexon_base_url}/datasets/{dataset}/stream",
                params=params,
                timeout=settings().http_timeout_seconds,
                headers={"Accept": "application/json", "User-Agent": "GridBricks/1.0"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Elexon connection failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            delay = 120.0
            retry = response.headers.get("Retry-After")
            if retry:
                try:
                    delay = float(retry)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(retry) - datetime.now(UTC)).total_seconds()
                    except (ValueError, TypeError):
                        pass
            raise UpstreamError(f"Elexon returned HTTP {response.status_code}", delay)
        try:
            data = response.json()
            if isinstance(data, dict):
                data = data["data"]
            if not isinstance(data, list):
                raise ValueError("Expected an array of observations")
        except (ValueError, KeyError) as exc:
            raise UpstreamError("Elexon returned an invalid data response") from exc
        checksum = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return data, checksum
