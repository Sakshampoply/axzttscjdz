# GridBricks

Wind forecast intelligence for day-ahead electricity decisions in Great Britain.

GridBricks keeps checking Elexon, remembers each forecast version, and compares the forecast available at a decision cutoff with actual wind generation. It supports both current forecasts and historical replay. January 2026 is a demonstration preset, not a hardcoded operating period.

## What users can do

- Review tomorrow's latest wind forecast, minimum output, publication time, and coverage.
- Reconstruct a previous decision using a London date and cutoff time, defaulting to 09:00.
- Compare eligible forecast publications and inspect downward revisions.
- Explicitly reveal subsequent actuals without changing the decision-time forecast.
- Evaluate MAE, bias, RMSE, WAPE, and coverage using daily bars, a heatmap, and an error distribution.
- Separate outcomes known before a decision from retrospective evaluation.
- Switch between source-publication replay and application-receipt replay.
- Download an immutable, traceable CSV assessment and print the displayed report.
- Inspect source freshness and request coalesced updates.

The application uses **WINDFOR and FUELHH filtered to WIND only**. Customer demand, contracted supply, electricity prices, other fuels, purchasing recommendations, order execution, and AI agents are outside its scope. National wind is not the client's contracted generation.

## Start with Docker

Requires Docker Engine and Docker Compose.

```bash
docker compose up --build -d
```

Open **http://localhost:8080**. PostgreSQL persists in the `pgdata` volume. The migration service completes before web and worker start. The independent worker prioritises current data and fills the preceding month in the background.

Load the January demonstration using the same ingestion pipeline:

```bash
docker compose exec web python -m app.cli demo
```

The command queues 30 December–1 February imports to include required boundary records. Leave the worker running, then select **January 2026** in the interface. Check import progress in **Data status**.

```bash
docker compose logs -f worker
docker compose stop
```

`stop` retains data. Removing the `pgdata` volume deletes the local database.

## Local development

Requires Python 3.12+, uv, Node.js 22+, and PostgreSQL 17. Docker can provide PostgreSQL alone:

```bash
cp .env.example .env
docker compose up -d db
uv sync --frozen
uv run python -m app.cli migrate
uv run python -m app.cli worker
```

In separate terminals:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` and `/health` to FastAPI. API documentation is at **http://127.0.0.1:8000/docs**.

Additional data commands:

```bash
uv run python -m app.cli sync
uv run python -m app.cli demo
uv run python -m app.cli backfill --start 2026-01-01 --end 2026-02-01 --enqueue
```

Omit `--enqueue` for a foreground import. The demo command is safe to repeat while its jobs are active; observation imports are idempotent.

## Architecture

```mermaid
flowchart LR
    E[Elexon WINDFOR and FUELHH WIND] --> W[Independent Python worker]
    W --> DB[(PostgreSQL)]
    U[React frontend on Vercel] --> API[FastAPI on Render]
    API --> DB
    API --> A[Shared analytics]
    A --> API
    API --> Q[Durable sync jobs in PostgreSQL]
    Q --> W
```

The worker checks the upstream APIs every two minutes. The browser refetches every 30 seconds. A stale page read also queues a refresh; simultaneous refresh requests share one active job. Repeated public refreshes are coalesced during a 60-second cooldown.

Jobs use `FOR UPDATE SKIP LOCKED`, expiring leases, and bounded retry times. Session advisory locks prevent overlapping fetches for the same dataset. Source `Retry-After` is honoured. Long outages create daily recovery jobs while current windows are prioritised. Recent history is reconciled daily to recover revisions and late records.

Successful imports commit raw evidence, new observations, and the progress marker atomically. Identical payload content is retained once and linked by checksum on subsequent checks. A changed value with the same source identity is retained in raw evidence, while its original normalised record is flagged and excluded from calculations. Malformed batches do not partially advance progress.

### Database tables

| Table | Responsibility |
| --- | --- |
| `source_fetches` | Request windows, timings, checksums, raw payloads, outcomes, errors |
| `wind_forecasts` | Unique target/publication versions, generation, first receipt, source references |
| `wind_actuals` | Actual outturn versions and their publication/receipt evidence |
| `sync_state` | Dataset progress, last successful checks, errors, retry deadlines |
| `sync_jobs` | Refresh/backfill payloads, active deduplication keys, leases, attempts |
| `analysis_runs` | Immutable parameters, calculation version, evidence, result snapshots |

### Directory guide

| Location | Contents |
| --- | --- |
| `app/analytics.py` | Cutoff selection, native timestamp alignment, metrics and findings |
| `app/sync.py`, `app/elexon.py` | Durable jobs, HTTP client, incremental imports and worker |
| `app/models.py`, `app/db.py` | SQLAlchemy models and database connections |
| `app/main.py` | Validated API, refresh coalescing, data health, frozen exports |
| `app/cli.py` | Migrations, worker, historical and current import commands |
| `frontend/src/` | React application, ECharts components, API types and styling |
| `migrations/` | Versioned Alembic database migrations |
| `tests/` | Calculation, API, ingestion and real-PostgreSQL concurrency tests |
| `docs/` | Methodology, deployment instructions and demonstration materials |
| `compose.yaml`, `Dockerfile` | Reproducible local and hosted containers |
| `render.yaml`, `frontend/vercel.json` | Render backend resources and Vercel frontend configuration |

## Analytical conventions

- **Decision-time forecast:** latest `publishTime` at or before the cutoff, selected per `startTime`.
- **Source replay:** publication-time reconstruction. It does not assert original network delivery latency.
- **Receipt replay:** additionally requires `first_seen_at` at or before the relevant information cutoff. A later historical import is not treated as originally received.
- **Actual revisions:** use the latest eligible actual publication by the evaluation cutoff.
- **Native alignment:** January WINDFOR is hourly; FUELHH is half-hourly. Compare the forecast with the actual half-hour beginning at the exact same `startTime`. Do not interpolate forecasts or claim coverage for every half-hour.
- **Error:** forecast minus actual. Positive means actual wind was below forecast.
- **MAE:** mean absolute error. **Bias:** mean signed error. **RMSE:** square root of mean squared error. **WAPE:** sum of absolute errors divided by sum of absolute actual generation, times 100.
- **Coverage:** matched targets divided by expected native targets. Missing values remain missing. Zero WAPE denominator yields unavailable.
- **Known history:** both forecast eligibility and actual publication/receipt eligibility respect the historical information cutoff.
- **January boundary:** 1–31 January decisions cover delivery on 2 January–1 February.
- **Clock changes:** UTC storage and London-aware delivery boundaries preserve 23/25-hour days and 46/50-half-hour days.

Historical errors are measured evidence, not guaranteed future uncertainty bounds. Operational outturn may be revised and is not a client-specific settled position. Forecast revisions are not independent probabilistic ensemble members. Summaries are deterministic templates; they do not infer weather causes or prices.

## Deployment

Target architecture: **Vercel frontend + Render API, worker, and PostgreSQL**. See [deployment guide](docs/DEPLOYMENT.md) for resource setup, environment variables, migration ordering, CORS, seeding, and public checks.

Deployment URLs are recorded in [deployment status](docs/DEPLOYMENT_STATUS.md). Unverified or uncreated service URLs are not presented as working deployments.

### Environment variables

| Variable | Default / meaning |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string; Render's `postgresql://` form is accepted |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins; set the exact Vercel production URL |
| `SYNC_INTERVAL_SECONDS` | `120` |
| `STALE_AFTER_SECONDS` | `300` |
| `REFRESH_COOLDOWN_SECONDS` | `60` |
| `JOB_LEASE_SECONDS` | `300` |
| `BOOTSTRAP_HISTORY_DAYS` | `30` |
| `BOOTSTRAP_DEMO` | `false`; Render blueprint sets true for one-time January queueing |
| `HTTP_TIMEOUT_SECONDS` | `30` |
| `VITE_API_BASE_URL` | Frontend build-time Render API origin; empty for same-origin Docker/local proxy |

## Verification

```bash
uv run pytest -q
cd frontend
npm run build
```

PostgreSQL-specific tests run against an explicitly named disposable `_test` database:

```bash
docker compose exec -T db createdb -U gridbricks gridbricks_test
TEST_DATABASE_URL=postgresql+psycopg://gridbricks:gridbricks@localhost:55432/gridbricks_test uv run pytest -q
```

Tests delete and recreate application tables **only in the isolated test database**. Unit tests use temporary SQLite databases; the PostgreSQL suite verifies advisory locks, concurrent job coalescing, and worker claims. CI runs both suites, builds the frontend, and checks container configuration.

Tests cover cutoff leakage, hidden actuals, original receipt semantics, February boundaries, clock changes, missing/zero values, real arithmetic fixtures, source conflicts, atomic failure, retry deadlines, duplicate imports, leases, and immutable CSV evidence. Browser verification should include January replay, reveal actuals, alternate publications, accuracy modes, export, refresh, mobile layout, and data-health inspection.

## Demonstration and submission

Use [the demonstration script](docs/DEMO_SCRIPT.md). The required video has two parts: a client-facing overview and a technical review, no more than five minutes each and ten minutes total. It must be uploaded as an unlisted YouTube video before submission. Public repository, application, and video links must work in incognito mode.

## AI assistance disclosure

This application, tests, documentation, and demonstration preparation were developed with OpenAI Codex assistance. All numerical analysis is performed by deterministic Python code; there is no LLM or autonomous trading agent in the application. Source behaviour was checked against Elexon records and documentation.

## Sources

- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Elexon wind generation definitions](https://bmrs.elexon.co.uk/wind-generation)
- [Elexon platform guidance](https://github.com/elexon-data/insights-docs/blob/main/docs/insights_data_platform.md)

Elexon is the source of the generation data. The application is independently developed and does not imply Elexon endorsement.
