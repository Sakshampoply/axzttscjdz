# Hosting and operations

## Existing services

| Component | Host | Address / configuration |
| --- | --- | --- |
| React/Vite frontend | Vercel | [gridbricks-wind.vercel.app](https://gridbricks-wind.vercel.app), project root `frontend` |
| FastAPI backend | Render Free Docker web service | [gridbricks-api.onrender.com](https://gridbricks-api.onrender.com) |
| PostgreSQL 17 | Render Free, Frankfurt | Private connection from the API; credentials are never committed |
| Scheduled collection | GitHub Actions | `.github/workflows/synchronise.yml`, shared refresh every five minutes |

The existing Git integrations build `main`. The Vercel frontend calls the Render API; it does not call Elexon directly. `render.yaml` contains only free plans. There is no paid worker, Redis instance or Render cron job.

## Local and hosted queue execution

Local Docker runs an independent worker with two-minute checks. The free hosted API instead uses `REQUEST_DRIVEN_SYNC=true`: requests schedule a bounded background runner against the same durable PostgreSQL queue. Current refreshes have priority over historical imports.

The hosted runner checks its 60-second budget between jobs; a single job may finish after that budget. Process and database advisory locks prevent concurrent runners. Dataset locks, atomic imports and expiring leases support recovery after process termination. Each subsequent refresh or dashboard read can continue pending work. The browser can close without cancelling stored jobs; the GitHub schedule provides later requests.

Missing historical selections reuse completed daily imports. The demonstration includes December 2025 through January 2026 and 1 February delivery. Source publication times, original receipt times and saved export evidence remain in PostgreSQL across application redeploys.

## Configuration

| Variable | Purpose / value |
| --- | --- |
| `DATABASE_URL` | Private PostgreSQL connection string; secret |
| `ALLOWED_ORIGINS` | Exact permitted frontend origins; current production is `https://gridbricks-wind.vercel.app` |
| `VITE_API_BASE_URL` | Public frontend build-time API origin; use the Render origin without a trailing slash |
| `REQUEST_DRIVEN_SYNC` | `true` for the free hosted API; `false` when using an independent worker |
| `SYNC_INTERVAL_SECONDS` | `300` hosted, `120` local worker |
| `REQUEST_JOB_BUDGET_SECONDS` | `60`, checked between hosted jobs |
| `STALE_AFTER_SECONDS` | `300`; freshness warning threshold |
| `REFRESH_COOLDOWN_SECONDS` | `60`; public refresh coalescing/cooldown |
| `JOB_LEASE_SECONDS` | `300`; interrupted work becomes reclaimable |
| `BOOTSTRAP_DEMO` | `true` to queue December/January once |
| `BOOTSTRAP_HISTORY_DAYS` | `30` recent days for ongoing accuracy analysis |

Vite's development proxy and same-origin Docker setup can use an empty `VITE_API_BASE_URL`. For a preview deployment, explicitly permit that intended frontend origin on the API. Do not broaden CORS to all origins as a shortcut.

## Recreate the deployment

1. Create equivalent Free Render resources from `render.yaml`, with PostgreSQL and the API in Frankfurt. Set the API's database URL to the internal connection string and leave external database access blocked.
2. Configure the API variables above. `python -m app.serve` runs Alembic under an advisory lock before starting FastAPI; a paid pre-deploy command is unnecessary.
3. Import the public repository into Vercel with root `frontend`, Vite build and `dist` output. Configure `VITE_API_BASE_URL`, then deploy.
4. Set Render's `ALLOWED_ORIGINS` to the resulting Vercel production origin.
5. Set GitHub repository variable `RENDER_API_URL` to the API origin. The workflow calls the public, rate-limited refresh endpoint without database credentials or an Elexon secret.
6. Request `POST /api/refresh` once. Inspect `/api/jobs/{id}` and `/api/data-quality` for completion, not merely HTTP acceptance. Later requests continue queued historical imports.

For manual workflow execution:

```bash
gh variable set RENDER_API_URL --body https://YOUR-API.onrender.com
gh workflow run synchronise.yml
```

## Free-host limits

This configuration provides a demonstration deployment with no availability or freshness SLA. Render can sleep after 15 idle minutes; GitHub schedules can be delayed, skipped, or disabled after 60 days without repository activity. Free instance hours are shared across a Render workspace, and repeated refresh requests consume those hours. Other bandwidth, build and service-initiated traffic limits also apply.

Free Render PostgreSQL has a 1 GB limit, no managed backups, and expires 30 days after creation. **The current database expires 23 November 2026.** Preserve required data before expiry. Another PostgreSQL database can be substituted through `DATABASE_URL`; no paid upgrade is enabled by this repository. Published source records can be reimported, but original receipt timestamps and saved analyses require a database backup to preserve.

References: [Render free services](https://render.com/docs/free), [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Verify a release

- Open the public frontend and repository without owner authentication; `/health` should return 200.
- The default selection should forecast 28 January using the 27 January 09:00 cutoff.
- Exactly two report tabs should share one applied selection; draft edits must not alter displayed or exported results.
- Both themes should style cards, controls, chart axes, lines, tooltips, warnings and loading states. The chosen theme should survive reload when storage is available.
- Previous forecast versions must predate the same cutoff. Hover a comparable target and check its MW/% revision and publication times.
- Evaluation must exclude unfinished periods and later publications, and expose percentages, historical frequency and P90 alongside coverage.
- Downloaded CSV should match the saved report, including comparison fields or window metric metadata. Earlier saved exports must remain readable.
- Check keyboard navigation, mobile overflow, source warnings and a manual/scheduled refresh through ingestion completion.
