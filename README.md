# GridBricks

Wind forecast intelligence for day-ahead electricity planning in Great Britain.

**[Open the application](https://gridbricks-wind.vercel.app)** · [Public repository](https://github.com/Sakshampoply/axzttscjdz) · [API health](https://gridbricks-api.onrender.com/health)

## What the product does

Choose a decision date and time, then press **View results**. Two tabs answer two questions using the same selection:

| Tab | Question it answers | What you see |
| --- | --- | --- |
| Forecast | What wind forecast was available when the decision had to be made, and what changed? | Next-day forecast, previous available version, changes in MW and %, and average/minimum/maximum output |
| Evaluation | How reliable were earlier day-ahead forecasts, using only evidence known at that moment? | Forecast versus actual wind, average miss, relative miss, tendency, coverage, historical shortfall frequency and larger-miss context |

The demonstration opens at **27 January 2026, 09:00 London time**. Forecast covers **28 January**. Evaluation uses the **previous 30 decision dates**, at the same clock time each day, and only actual periods completed and published by the selected moment.

Editing the inputs does not silently change either report. Press View results to apply the new selection. Each tab has three summary cards, one chart, and a CSV download. The Forecast chart restores the previous forecast as a dashed line; its tooltip includes both publication times and the change. There are no separate current/historical modes or later-outcome toggles.

Use the sun/moon button to switch between **light and dark mode**. The first visit follows the device preference, with dark as the fallback. A saved choice is applied before the page paints and persists across reloads when browser storage is available.

![Forecast in light mode](docs/media/forecast-light.png)

![Evaluation in dark mode](docs/media/evaluation.png)

## Does it tell the client how much electricity to buy?

**It quantifies national wind forecast uncertainty; it does not calculate a client purchase quantity.** The assignment supplies only national Elexon wind forecasts and actual wind generation. It provides no customer demand profile, client wind entitlement, existing purchases, other contracted generation, prices, or risk policy.

For a particular delivery period, a planning calculation would start with expected customer consumption minus supply already secured, including the wind that actually belongs to that client's portfolio. That requires additional inputs. National wind generation cannot be subtracted directly from one utility's demand, and past national forecast error cannot be added directly to its purchase order.

The useful output here is evidence: what wind was expected, how the forecast changed, and how large earlier misses were. That supports the utility's separate procurement process within the assignment's wind-only scope. [NESO's BSC overview](https://www.neso.energy/industry-information/codes/balancing-settlement-code-bsc) explains the relationship between physical generation/demand, contracted positions and imbalance settlement.

**MW** measures power at a rate; **MWh** measures energy over a period. For example, 100 MW sustained for half an hour is 50 MWh. This application preserves source target values in MW and does not invent a whole-hour energy profile from the half-hour actual used for matching.

## Understand the evaluation

| Measure | Plain-language meaning |
| --- | --- |
| Average forecast miss (MAE), MW | Typical size of a historical miss, ignoring direction |
| Relative miss (WAPE), % | Total absolute miss as a percentage of total actual wind across matched targets |
| Forecast tendency, MW and % | Whether forecasts tended to be above or below actual wind, and by how much |
| Coverage, count and % | How many completed target periods have both eligible forecast and actual data |
| Wind below forecast, % | How often actual wind was below forecast among evaluated historical targets |
| Larger historical miss (P90), MW | The 90th percentile of historical absolute errors, showing a larger-miss scale |

These measures complement each other. Coverage is data completeness, not forecast accuracy. WAPE is not an accuracy score, and `100 − WAPE` is not a probability of being right. The historical shortfall rate and P90 are descriptive statistics, not tomorrow's probability or a guaranteed safety margin. Missing values remain gaps; zero is a real observation. Percentages with a zero denominator are unavailable rather than infinite.

See [calculation methods and examples](docs/METHODOLOGY.md) for formulas, publication cutoffs, source alignment, clock changes and export details.

## Run locally

Requires Docker Engine and Docker Compose:

```bash
docker compose up --build -d
docker compose exec web python -m app.cli demo
```

Open [localhost:8080](http://localhost:8080). The demo queues **1 December 2025–1 February 2026**, giving early-January decisions the preceding history needed for evaluation. PostgreSQL data persists in the `pgdata` volume. The migration service finishes before the API and independent worker start.

```bash
docker compose logs -f worker
docker compose stop
```

Other selections use the same code. Missing days are imported through durable jobs, with a short loading or unavailable-data message. Concurrent viewers share jobs. Failed imports can be retried with View results. Stopping retains stored data; removing the database volume deletes it.

### Develop the API and frontend separately

Requires Python 3.12+, uv, Node.js 22+, and PostgreSQL 17:

```bash
cp .env.example .env
docker compose up -d db
uv sync --frozen
uv run python -m app.cli migrate
uv run python -m app.cli worker
```

Run the API and frontend in two further terminals:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm ci
npm run dev
```

Open [127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies API requests to FastAPI. Setting `REQUEST_DRIVEN_SYNC=true` on the API enables bounded queue processing after requests instead of a resident worker.

## Architecture

```mermaid
flowchart LR
    UI[React interface] --> API[FastAPI]
    API --> C[Shared cutoff and calculation code]
    C --> DB[(PostgreSQL)]
    API --> Q[Durable import / refresh queue]
    G[GitHub scheduled request] --> API
    Q --> W[Bounded runner or local worker]
    W --> E[Elexon WINDFOR / FUELHH WIND]
    W --> DB
```

The browser reads FastAPI, which serves stored evidence from PostgreSQL. The ingestion process checks for new upstream records, retains forecast versions, and commits validated records and progress atomically. This makes repeat views fast and preserves useful evidence during source outages. The same ingestion and calculation code handles January and other dates.

The local worker checks every two minutes. The free hosted setup uses GitHub refresh requests targeting five-minute checks, with bounded processing in the Render API. Screens refresh stored results every 30 seconds. Publication time and last successful source check are displayed separately; an unchanged forecast can still be the latest available one.

| Table | Responsibility |
| --- | --- |
| `source_fetches` | Request parameters, raw responses, checksums, timing and failures |
| `wind_forecasts` | Target/publication forecast versions and source references |
| `wind_actuals` | Actual-generation observations and source publication times |
| `sync_state` | Progress and last successful source checks |
| `sync_jobs` | Durable refresh/import work, deduplication, attempts and expiring leases |
| `analysis_runs` | Frozen parameters, methods, evidence and result snapshots for exports |

Dataset locks, queue coalescing and expiring leases protect concurrent imports and restart recovery. Conflicting source records are retained and flagged. UTC timestamps are stored; the interface displays London time.

## Repository map

| Path | Contents |
| --- | --- |
| `frontend/src/main.tsx` | Shared decision form, two report panels, theme toggle, downloads |
| `frontend/src/charts.tsx`, `theme.ts`, `styles.css` | Forecast comparison, evaluation chart and theme-aware responsive styling |
| `frontend/src/api.ts` | Typed dashboard contract and request handling |
| `app/dashboard.py` | Simplified reports, revision percentages and historical risk context |
| `app/analytics.py`, `timeutils.py` | Forecast selection, alignment, metrics, time handling and fingerprints |
| `app/main.py` | Dashboard API, validation, refresh jobs and immutable exports |
| `app/elexon.py`, `sync.py`, `cli.py` | Source client, validation, imports, scheduling, retries and commands |
| `app/models.py`, `db.py`, `migrations/` | SQLAlchemy models, connections and Alembic migrations |
| `tests/` | Calculation, API, ingestion, export and PostgreSQL concurrency checks |
| `Dockerfile`, `compose.yaml` | Container builds, local database, migrations, API and worker |
| `render.yaml`, `frontend/vercel.json`, `.github/workflows/` | Hosting, verification and free scheduled collection |
| `docs/` | [Methods](docs/METHODOLOGY.md), [deployment](docs/DEPLOYMENT.md), [verification](docs/DEPLOYMENT_STATUS.md) and screenshots |

## API and exports

```text
GET /api/dashboard?decision_date=2026-01-27&decision_time=09:00
```

Both fields are required and represent London time. The response contains `selection`, `forecast`, `evaluation`, `source` and `history`. Both reports share one cutoff; users cannot enable later evidence. New reports use method `decision-dashboard-v3`.

Downloads first save the visible report using `POST /api/analysis-runs` with `dashboard: true`, its kind (`forecast` or `accuracy`), the two selection fields in `parameters`, and `expected_fingerprint`. A source change returns 409 instead of silently exporting different data. `GET /api/export?run_id=...` returns frozen CSV; `format=json` includes the complete saved report. Previous saved exports remain readable.

Forecast CSV includes both versions, their publication times, and MW/% changes. Evaluation CSV includes matched values, errors and window-level percentage/P90 metadata. Missing fields are blank. Freshness clocks do not affect evidence fingerprints.

Operational routes are `/health`, `/api/data-quality`, `/api/refresh` and `/api/jobs/{id}`. Legacy read APIs remain compatible but do not add interface modes. See [deployment configuration](docs/DEPLOYMENT.md) for environment variables.

## Verify

```bash
uv run ruff check app tests
uv run pytest -q
npm run build --prefix frontend
```

To include real PostgreSQL concurrency checks, create a disposable test database once and run:

```bash
docker compose exec -T db createdb -U gridbricks gridbricks_test
TEST_DATABASE_URL=postgresql+psycopg://gridbricks:gridbricks@localhost:55432/gridbricks_test uv run pytest -q
```

The tests recreate application tables only in the explicitly named test database. Browser verification covers the shared applied selection, both themes and persistence, comparison tooltips, downloads, keyboard access and mobile layouts.

## Hosting limits and AI disclosure

The frontend runs on Vercel; the API and PostgreSQL run on free Render services. The current database expires **23 November 2026**. Free-host sleep, quota limits, delayed schedules and upstream delays mean there is no freshness SLA. See [deployment instructions](docs/DEPLOYMENT.md) before operating or moving this setup.

The application, tests and documentation were developed with **OpenAI Codex assistance**. Product calculations are deterministic Python code. The application does not call an LLM or use an AI agent.

Sources: [WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream), [FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream), [Elexon wind definitions](https://bmrs.elexon.co.uk/wind-generation). Only `fuelType=WIND` actuals are used. GridBricks is independently developed and does not imply Elexon endorsement.
