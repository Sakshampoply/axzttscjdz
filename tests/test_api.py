import csv
import io

from fastapi.testclient import TestClient

from app.main import app


def test_api_validates_ranges_and_modes():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/forecast?mode=unknown").status_code == 422
        assert client.get("/api/accuracy?start=2026-02-01&end=2026-01-01").status_code == 422
        assert client.get("/api/accuracy?start=2026-01-01&end=2026-01-02&basis=known").status_code == 422


def test_refresh_endpoint_coalesces_public_requests():
    with TestClient(app) as client:
        first = client.post("/api/refresh").json()
        second = client.post("/api/refresh").json()
        assert first["id"] == second["id"]
        assert client.get(f"/api/jobs/{first['id']}").json()["status"] == "pending"


def test_export_freezes_exact_visible_analysis(seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 80)
    with TestClient(app) as client:
        result = client.get("/api/forecast?mode=replay&decision_date=2026-01-01&reveal_actuals=true").json()
        parameters = {
            k: result[k]
            for k in (
                "mode",
                "decision_date",
                "decision_time",
                "availability",
                "reveal_actuals",
                "as_of",
                "evaluation_at",
            )
        }
        request = {
            "kind": "forecast",
            "parameters": parameters,
            "expected_fingerprint": result["fingerprint"],
        }
        response = client.post("/api/analysis-runs", json=request)
        assert response.status_code == 201, response.text
        run_id = response.json()["id"]
        assert client.post("/api/analysis-runs", json=request).json()["id"] == run_id
        seed("actual", "2026-01-02T00:00Z", "2026-01-03T00:00Z", 50)
        exported = client.get(f"/api/export?run_id={run_id}")
        records = list(csv.DictReader(io.StringIO(exported.text)))
        assert float(records[0]["actual_mw"]) == 80
        assert float(records[0]["error_mw"]) == 20
        assert records[0]["analysis_id"] == run_id
        assert client.post("/api/analysis-runs", json=request).status_code == 409


def test_exports_never_reveal_hidden_actuals(seed):
    seed("forecast", "2026-01-02T00:00Z", "2026-01-01T07:30Z", 100)
    seed("actual", "2026-01-02T00:00Z", "2026-01-02T00:30Z", 80)
    with TestClient(app) as client:
        result = client.get("/api/forecast?mode=replay&decision_date=2026-01-01").json()
        params = {
            k: result[k]
            for k in (
                "mode",
                "decision_date",
                "decision_time",
                "availability",
                "reveal_actuals",
                "as_of",
                "evaluation_at",
            )
        }
        run = client.post(
            "/api/analysis-runs",
            json={"kind": "forecast", "parameters": params, "expected_fingerprint": result["fingerprint"]},
        ).json()
        rows = list(csv.DictReader(io.StringIO(client.get(f"/api/export?run_id={run['id']}").text)))
        assert rows[0]["actual_mw"] == ""
        assert rows[0]["actual_id"] == ""
