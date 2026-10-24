# GridBricks demonstration

Target: approximately eight minutes total. Keep the customer section and technical section under five minutes each. Use actual imported Elexon records. Never imply hypothetical data or unverified hosting is live.

## Part one Client walkthrough

### 00:00 to 00:35 The problem

“GridBricks helps a day-ahead electricity buying team understand the wind forecast they had when making a decision, and how reliable that information has been. Wind is weather dependent. A forecast can change, so the version available at the buying decision matters. This application focuses on national wind intelligence. It does not calculate the client's purchase quantity because demand and contracted supply are not supplied.”

Show the current dashboard, publication time, and data status.

### 00:35 to 01:10 Continuous updates

“A GitHub schedule targets checks every five minutes, stores each forecast version, and refreshes the screen every thirty seconds. Scheduled collection works with the browser closed. This free deployment can experience cold starts, quota limits, and scheduler delays. Publication time and last checked are separate: an unchanged forecast can still be the latest one. Check for updates shares a background job across users.”

Open Data status, then close it.

### 01:10 to 02:00 Reconstruct the decision

Select January 2026. Confirm 27 January, 09:00, for 28 January delivery.

“Here we have stepped back to 09:00 on 27 January. Every delivery target uses the latest forecast published before this cutoff. Later forecasts are excluded. The cards show the average expected wind, its lowest period, earlier measured error, and whether the curve is complete.”

Explain the native target and publication labels. Select an earlier eligible comparison publication to show revisions when present. Avoid claiming that repeated identical source versions contain changes.

### 02:00 to 02:45 Reveal the outcome

Enable Show what actually happened and open underlying values.

“The additional line shows what subsequently happened. The forecast remains locked to the original decision. A positive error means actual wind was below forecast. The table and export show the individual records supporting the result.”

### 02:45 to 03:45 Quantify reliability

Open Accuracy, use January 1–31 and retrospective evaluation. Show daily bars, the histogram, and the heatmap. Read metric values from the running application rather than memorising them.

“MAE is the average absolute miss in MW. Bias shows direction; positive means over-forecasting. RMSE gives large misses greater weight. Coverage tells us how much evidence is present. The heatmap reveals delivery periods hidden by a monthly average.”

Switch to Known before this decision.

“This version excludes actuals published after our historical decision. It prevents hindsight from appearing as information the trader already had. Historical error is evidence, not a guarantee about tomorrow.”

### 03:45 to 04:00 Export

Return to Forecast and export CSV.

“The export freezes the displayed calculation with its cutoff, method version, and source references.”

## Part two Technical walkthrough

### 04:00 to 04:45 Architecture

Show the README architecture diagram.

“React is served on Vercel. FastAPI and PostgreSQL use free Render services. Scheduled requests run a bounded processor in the API; the same code also supports a separate local Docker worker. Free Render PostgreSQL expires after thirty days, so longer operation requires a replacement database. The browser does not call Elexon. PostgreSQL is a continuously updated record of forecasts, rather than a one-time cache.”

### 04:45 to 05:40 Reliable ingestion

Show `app/sync.py` and database models.

“The worker uses overlapping publication windows, durable daily recovery jobs, and idempotent source identities. Imports and progress commit atomically. Conflicting values are retained as evidence and excluded from normal calculations. PostgreSQL locks coalesce refreshes and prevent overlapping dataset fetches. Expiring leases recover interrupted jobs. Retry-After is respected.”

### 05:40 to 06:30 Analysis and time

Show `app/analytics.py` and the methodology tab.

“Selection is performed per target timestamp with publishTime no later than the decision. Application receipt replay adds first_seen_at. Actuals have their own evaluation cutoff. UTC storage and London-aware boundaries handle clock changes. January decisions include February 1 delivery. Hourly WINDFOR targets are compared with FUELHH half-hours starting at the same timestamp; no extra forecasts are interpolated.”

### 06:30 to 07:15 Evidence and exports

Show `app/main.py`, OpenAPI documentation, and a downloaded CSV.

“Charts and exports use the same analytical functions. Export creation checks the displayed evidence fingerprint. If evidence changed, the user must refresh rather than unknowingly export different results. Saved snapshots preserve the original result after later source revisions.”

### 07:15 to 08:00 Tests and handover

Show passing test output, Docker Compose, and deployment documentation.

“Tests cover cutoff leakage, hidden actuals, receipt replay, native alignment, missing and zero values, February and daylight-saving boundaries, atomic failure, retries, and immutable exports. Separate real-PostgreSQL tests verify concurrent refresh coalescing, worker claims, and advisory locks. Docker starts migrations, API, worker, and database. The README includes setup, methodology, limitations, and explicit Codex assistance disclosure.”

Finish before ten minutes. Upload as unlisted, then verify the video, deployed application, and repository in incognito mode before submission.
