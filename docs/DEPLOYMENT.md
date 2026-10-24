# Deployment on Vercel and Render

## Resources

- Vercel: React static frontend; project root `frontend`.
- Render: Docker web API, continuously running Docker worker, and PostgreSQL 17.
- All Render resources use Frankfurt so the API and worker can use the database's internal network address.

`render.yaml` defines persistent paid service tiers to support a continuously running worker. Review the resource prices in Render before creating them. A sleeping free web service does not provide the same freshness behaviour as an always-running worker.

## Render

1. Create a Blueprint from the public repository and select `render.yaml`.
2. Set `ALLOWED_ORIGINS` to the intended Vercel production origin. For a temporary test before the frontend exists, use a placeholder origin and replace it before testing in the browser.
3. Confirm the database, web service, and worker resources and their costs.
4. Deploy. The web pre-deploy command runs Alembic migrations. Worker startup also runs the same migrations under a database advisory lock, avoiding first-deploy ordering races.
5. Check the API's `/health` and `/api/data-quality` endpoints. The latter reports dataset freshness and import jobs.

The database accepts private Render network connections only. Connection strings are passed through environment variables, never committed. Use Render's authorised shell or environment access for administrative commands rather than opening the database to the public internet.

The worker has `BOOTSTRAP_DEMO=true`, which queues the January demonstration once when absent. It also queues the preceding month. Existing current data is fetched first. Source requests are bounded and historical import jobs persist across restarts.

## Vercel

1. Import the same GitHub repository as a Vercel project.
2. Set root directory to `frontend`; Vite configuration is included.
3. Set `VITE_API_BASE_URL` to the Render API origin, without a trailing slash. This is public configuration, not a secret.
4. Deploy the frontend.
5. Set Render's `ALLOWED_ORIGINS` to the exact resulting Vercel origin and redeploy the API configuration.
6. Confirm the public application can reach the API and does not require deployment-owner authentication.

Vercel previews use different origins. Explicitly add an intended preview origin to Render's allowlist when testing it. Do not use wildcard credentialed CORS.

## Public acceptance checks

- Application and repository load in an incognito window.
- Current forecasts appear with an accurate last-checked time.
- January replay selects 27 January at 09:00 for 28 January delivery.
- Revealing actuals changes the comparison, not the selected forecast.
- January accuracy has the expected native target counts once imports finish.
- Repeated refresh requests return the same active job.
- CSV download matches the visible calculation and includes source references.
- `/health` returns HTTP 200 and worker logs show continued checks while the browser is closed.
- The unlisted YouTube video is playable without signing in.

## Maintenance

Enable managed database backups appropriate to the account and verify restoration into a separate database. Deploy compatible additive migrations before code that depends on them. Keep one scheduled worker by default; row and advisory locks protect against accidental overlap. Monitor dataset check age and failures separately from the age of forecast publications.

For failures, inspect `source_fetches`, `sync_jobs`, and `/api/data-quality`. Existing evidence is retained during upstream outages. A source conflict is flagged and excluded rather than silently rewriting history.
