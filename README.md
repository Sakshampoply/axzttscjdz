# GridBricks

A simple wind forecast dashboard for day-ahead electricity decisions in Great Britain.

Choose a **decision date and time**, press **View results**, and use the two tabs:

- **Forecast** shows expected wind output for the following delivery day, using forecasts published by your decision time.
- **Evaluation** compares earlier day-ahead forecasts with actual wind generation over the preceding 30 decision dates. It uses only outcomes available by your selected moment.

The initial selection is **27 January 2026 at 09:00 London time**, for delivery on 28 January. The same applied selection controls both tabs. Editing the inputs does not change results until View results is pressed. Each tab contains three summary cards, one chart, a compact source status, and a CSV download.

The application uses Elexon **WINDFOR** and **FUELHH filtered to WIND** only. There is no customer demand input, client purchase-volume calculation, electricity pricing, order execution, or AI agent.

## Start locally

Requires Docker Engine and Docker Compose:

```bash
docker compose up --build -d
```

Open [localhost:8080](http://localhost:8080). PostgreSQL persists in the `pgdata` volume. The migration service completes before the web application and independent sync worker start.

Import the January demonstration and its earlier evaluation history:

```bash
docker compose exec web python -m app.cli demo
```

This queues **1 December 2025–1 February 2026**, covering January decisions and the preceding evaluation history. The dashboard also queues missing days for any selected date. Existing data appears immediately; a short message indicates when more records are being imported. Previously completed imports are reused, and concurrent users share jobs. Failed imports can be retried with View results.

```bash
docker compose logs -f worker
docker compose stop
```

Stopping retains data. Removing the `pgdata` volume deletes the local database.

### Develop without containers for the application

Requires Python 3.12+, uv, Node.js 22+, and PostgreSQL 17. Start PostgreSQL with Docker, then run:

```bash
cp .env.example .env
docker compose up -d db
uv sync --frozen
uv run python -m app.cli migrate
uv run python -m app.cli worker
```

In two further terminals:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm ci
npm run dev
```

Open [127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies API calls to FastAPI. Alternatively, `REQUEST_DRIVEN_SYNC=true` on the API runs bounded queue processing after dashboard requests, without a resident local worker.

## How the calculations work

All timestamps are stored in UTC and interpreted or displayed in **Europe/London**, including clock changes. The entered time is a decision moment, not a delivery time. Future, nonexistent, or ambiguous decision times are rejected with a clear message.

### Next-day forecast

For each target in the following delivery day, select the latest forecast whose `publishTime` is at or before the decision moment. Later publications and actual outcomes do not appear in this report. Average, minimum and maximum use available native forecast targets; missing values stay missing.

### Earlier evaluation

For a decision date D, the previous 30 decision dates are **D−30 through D−1**. Each uses the same selected London clock time on its own decision day and forecasts its following delivery day. Only delivery periods completed by the overall selected moment are included. Actual records, including revisions, must also have been published by that moment.

For example, 27 January at 09:00 evaluates decisions from **28 December–26 January**, covering delivery from **29 December up to completed periods on 27 January**. Later January outcomes are excluded automatically. Unfinished periods do not lower scoring coverage.

For earlier daily cutoffs across clock changes, a repeated clock time uses its first occurrence; a clock time skipped in spring moves forward by the clock-change gap. The actual user-entered decision time is always validated strictly.

WINDFOR targets in the January data are hourly and FUELHH actuals are half-hourly. Compare exact `startTime` values: a forecast target is matched with the actual half-hour beginning at that timestamp. No additional forecasts are interpolated. Original source resolution and missing-data gaps are preserved.

| Measure | Calculation | Meaning |
| --- | --- | --- |
| Error | Forecast − actual | Positive means actual wind was below forecast |
| Average miss (MAE) | Mean absolute error | Typical size of the miss, in MW |
| Forecast tendency (bias) | Mean signed error | Whether forecasts tended to be above or below actual wind |
| Coverage | Matched targets ÷ expected completed targets | How much eligible evidence was available |
| RMSE | Square root of mean squared error | Greater emphasis on large misses; retained in saved results |
| WAPE | Sum of absolute errors ÷ sum of absolute actual generation × 100 | Aggregate relative error; unavailable for a zero denominator |

Historical error is evidence, not a guaranteed future error range. Source publication times reconstruct published information; a later import does not prove when a client originally received it. The database retains original application receipt timestamps for auditing.

## Architecture and source layout

```mermaid
flowchart LR
    UI[React: shared decision time and two tabs] --> API[FastAPI dashboard endpoint]
    API --> DB[(PostgreSQL)]
    API --> A[Cutoff-safe calculations]
    API --> Q[Durable import and refresh jobs]
    G[GitHub five-minute schedule] --> API
    Q --> W[Bounded runner or local worker]
    W --> E[Elexon WINDFOR and FUELHH WIND]
    W --> DB
```

| Location | Responsibility |
| --- | --- |
| `frontend/src/main.tsx` | Shared draft/applied selection, Forecast and Evaluation panels, CSV downloads |
| `frontend/src/charts.tsx`, `styles.css`, `api.ts` | Two line charts, dark responsive styling, typed dashboard contract |
| `app/dashboard.py` | One decision cutoff and fixed evaluation window; simplified reports |
| `app/analytics.py` | Native alignment, selection, metrics, fingerprints and legacy calculations |
| `app/main.py` | API validation, dashboard, refresh, saved analyses and exports |
| `app/sync.py`, `elexon.py`, `cli.py` | Coalesced jobs, validated imports, retries, live updates and historical recovery |
| `app/models.py`, `db.py`, `migrations/` | SQLAlchemy schema and Alembic migrations |
| `tests/` | Calculation, API, ingestion, exports and real-PostgreSQL concurrency tests |
| `Dockerfile`, `compose.yaml`, `render.yaml`, `frontend/vercel.json` | Containers and hosting configuration |
| `docs/` | Deployment instructions, implementation status and interface screenshots |

The six existing database tables are retained: `source_fetches`, `wind_forecasts`, `wind_actuals`, `sync_state`, `sync_jobs`, and `analysis_runs`. Forecast target/publication identities remain immutable. Imports and progress commit atomically. Conflicting source values are retained and flagged. Dataset advisory locks, queue coalescing, retry windows, and expiring job leases protect synchronisation.

### Dashboard API

```text
GET /api/dashboard?decision_date=2026-01-27&decision_time=09:00
```

Both fields are required and represent London time. The response contains `selection`, `forecast`, `evaluation`, `source` freshness, and `history` import status. Report fingerprints exclude volatile freshness/import status. Both reports use the same cutoff, with no client-controlled analysis modes.

New CSV assessments use `POST /api/analysis-runs` with `dashboard: true`, the report kind (`forecast` or `accuracy`), the two selection fields in `parameters`, and its `expected_fingerprint`. The server recalculates that report before saving; a changed fingerprint returns 409 so a download cannot silently differ from visible results. `GET /api/export?run_id=...` downloads the frozen rows. Existing saved analyses and legacy read APIs remain compatible.

Other operational endpoints are `/health`, `/api/data-quality`, `/api/refresh`, and `/api/jobs/{id}`. A refresh may optionally include the same date/time query parameters to retry failed historical imports.

## Hosting and configuration

The existing hosting setup uses a **Vercel frontend**, **free Render API and PostgreSQL**, and **GitHub scheduled refresh requests**. See [deployment instructions](docs/DEPLOYMENT.md) and [implementation status](docs/DEPLOYMENT_STATUS.md) for URLs and verification state.

The free hosted schedule targets five-minute checks. Local Docker uses a two-minute worker. Screens recheck stored results every 30 seconds. Free-host sleep, shared quotas, upstream publication delays and GitHub schedule delays prevent a freshness SLA. Free Render PostgreSQL expires after 30 days; the existing instance expires **23 November 2026**. Another PostgreSQL database can be substituted through `DATABASE_URL`.

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string; never commit credentials |
| `ALLOWED_ORIGINS` | Exact frontend origins allowed by FastAPI |
| `SYNC_INTERVAL_SECONDS` | `120` for the local worker; `300` for hosted schedule metadata |
| `REQUEST_DRIVEN_SYNC` | `true` for bounded processing inside the free hosted API |
| `REQUEST_JOB_BUDGET_SECONDS` | `60`, checked between jobs |
| `STALE_AFTER_SECONDS` | `300` |
| `REFRESH_COOLDOWN_SECONDS` | `60` |
| `JOB_LEASE_SECONDS` | `300` |
| `BOOTSTRAP_HISTORY_DAYS` | `30` |
| `BOOTSTRAP_DEMO` | Queue December/January records once when enabled |
| `VITE_API_BASE_URL` | Frontend build-time API origin; empty for the local proxy or same-origin Docker |

## Verify

```bash
uv run ruff check app tests
uv run pytest -q
npm run build --prefix frontend
```

Run PostgreSQL concurrency tests against an explicitly named disposable test database:

```bash
docker compose exec -T db createdb -U gridbricks gridbricks_test
TEST_DATABASE_URL=postgresql+psycopg://gridbricks:gridbricks@localhost:55432/gridbricks_test uv run pytest -q
```

Tests recreate application tables only inside the isolated test database. Browser checks cover two-tab navigation, applied selection, date changes, dark styling, mobile layout, loading/error states, chart tooltips, and CSV downloads.

## AI assistance disclosure and data sources

The application, tests and documentation were developed with OpenAI Codex assistance. All calculations and summaries use deterministic Python code; the application does not call an LLM.

- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Elexon wind definitions](https://bmrs.elexon.co.uk/wind-generation)

GridBricks is independently developed and does not imply Elexon endorsement.
