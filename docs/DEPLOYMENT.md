# Free deployment on Vercel and Render

## Resources and scheduling

- Vercel: static React frontend, project root `frontend`.
- Render: one **Free** Docker web service and one **Free** PostgreSQL 17 database in Frankfurt.
- GitHub Actions: the public repository's `Synchronise Elexon` workflow requests a shared refresh job every five minutes. There is no paid worker or cron service.

`render.yaml` contains only free plans. `REQUEST_DRIVEN_SYNC=true` runs a bounded job processor after a stale dashboard read or manual/scheduled refresh request. Responses use stored results immediately. The runner prioritises current data, then imports history for up to 60 seconds between jobs. It uses a process lock and PostgreSQL advisory lock, plus the same durable leases and dataset locks as the standalone worker. A stopped runner leaves jobs recoverable. No timer depends on an open browser.

**This free setup has no freshness or availability SLA.** GitHub schedules can be delayed, skipped, or disabled after 60 days without repository activity. Render can sleep after 15 idle minutes and cold-start on the next request. Its 750 monthly free instance hours are shared across the workspace, including other apps. Five-minute requests can keep this service awake and consume that allowance. Quota exhaustion can suspend free services. Source delays and failures are visible independently of scheduler delays. The View results action can request stored results while the API is running.

**Free Render PostgreSQL expires 30 days after creation**, has a 1 GB limit, and no managed backups. The instance created for this build expires **23 November 2026**. It must be replaced or migrated before expiry to preserve application availability. No paid upgrade is enabled by this project. Keep independent logical backups if receipt history and saved assessments must survive expiry; historical published records can be reimported, but original receipt times cannot be recreated. Another PostgreSQL provider can be substituted using `DATABASE_URL` without changing analytics.

References: [Render free limits](https://render.com/docs/free), [GitHub scheduled workflow limits](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Render setup

1. Create the free database and free web service from `render.yaml`, or create equivalent resources in the dashboard. All resources must explicitly show **Free**.
2. Set `DATABASE_URL` to the database's **internal** connection string. Keep external inbound database access blocked.
3. Set `ALLOWED_ORIGINS` to the exact Vercel application origin. Set `REQUEST_DRIVEN_SYNC=true`, `SYNC_INTERVAL_SECONDS=300`, `BOOTSTRAP_DEMO=true`, and `BOOTSTRAP_HISTORY_DAYS=30`.
4. Deploy. `python -m app.serve` runs Alembic migrations under an advisory lock before starting FastAPI; a paid pre-deploy feature is unnecessary.
5. Request `/api/refresh` once. Current data is checked first; January and preceding-month history are queued automatically. Additional requests continue pending imports. `/api/data-quality` reports jobs and dataset status.

The checked-in Docker Compose setup has a separate local worker checking every two minutes. It is an alternative execution mode for the same queue and code. Do not run a paid Render worker for the free deployment.

## Vercel setup

1. Import the public repository as a Vercel project with root `frontend`.
2. Use the included Vite build configuration and `dist` output.
3. Set `VITE_API_BASE_URL` to the Render API origin without a trailing slash. This is public configuration, not a secret.
4. Deploy and set Render's `ALLOWED_ORIGINS` to the resulting Vercel production origin.
5. Verify the production application loads without owner authentication. Explicitly allow an intended preview origin when testing preview deployments.

## Enable scheduled collection

Set the public repository variable `RENDER_API_URL` to the Render API origin. The workflow uses only a public, rate-limited refresh endpoint; it does not need database credentials or an Elexon secret.

```bash
gh variable set RENDER_API_URL --body https://YOUR-API.onrender.com
gh workflow run synchronise.yml
```

The five-minute schedule is offset from the top of the hour. Concurrency prevents overlapping workflow runs. Its successful HTTP response confirms job acceptance; inspect the job and source check times for successful ingestion. GitHub's standard hosted runners are free for public repositories within its service terms. No recurring Codex automation is required.

## Acceptance checks

- Public application and repository load without signing in.
- `/health` returns 200; `/api/data-quality` reports `scheduled_requests` mode.
- A manual refresh is accepted and its job completes; repeated requests share its identity.
- A GitHub workflow run accepts a refresh while the dashboard is closed.
- The default decision selects 27 January at 09:00 for 28 January delivery.
- Evaluation automatically uses the prior 30 decision dates and only completed outcomes known by that moment.
- Both tabs use one applied date/time and expose no analysis-mode controls.
- CSV matches its frozen evidence, including source references.
- Free plan and expiry limitations remain documented; no paid resources are provisioned.
