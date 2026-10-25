# Application and verification

## Public links

- Application: [gridbricks-wind.vercel.app](https://gridbricks-wind.vercel.app)
- API readiness: [gridbricks-api.onrender.com/health](https://gridbricks-api.onrender.com/health)
- Source: [Sakshampoply/axzttscjdz](https://github.com/Sakshampoply/axzttscjdz)

Vercel and Render build the `main` branch through the existing Git integrations. The API and PostgreSQL remain on Free plans. The current database expires **23 November 2026**; see [deployment and operations](DEPLOYMENT.md) for configuration and limits.

## Current experience

One decision date/time controls two tabs, Forecast and Evaluation. Draft edits do not alter results until View results is pressed. A sun/moon button switches light and dark mode and saves the choice when storage is available.

Forecast restores the previous eligible version as a dashed comparison line, with MW/% revisions, publication times in the tooltip and CSV, and the biggest-change summary. Evaluation keeps three cards and adds WAPE, normalised bias, historical below-forecast frequency and P90 absolute miss. These describe national wind reliability, not a client purchase volume.

![Forecast in light mode](media/forecast-light.png)

![Evaluation in dark mode](media/evaluation.png)

Other views: [dark Forecast](media/forecast.png), [light Evaluation](media/evaluation-light.png).

## Verification on 26 October 2026

- **50 Python tests pass**, including PostgreSQL concurrency checks, cutoff selection, later-publication exclusion, empty/zero-denominator metrics, revision calculations, durable imports and frozen exports.
- The frontend production build, Python lint/format checks and Docker Compose configuration pass.
- Browser verification confirms both themes, persistence after reload, keyboard theme/tab access, comparison tooltip values and CSV actions.
- At 360-pixel mobile width, controls/cards/context stack and the page has no horizontal overflow. Desktop retains three summary cards.
- Forecast CSV includes 24 default targets, both versions, their source publication times and MW/% revisions. Evaluation CSV contains 705 completed targets and the same aggregate percentage/P90 values as its saved report.
- Previously saved reports retain their method and schema. New reports use `decision-dashboard-v3`; no database migration is needed.

At the default **27 January 2026, 09:00** selection, evaluation contains **705/705 completed targets**, with:

| Measure | Value |
| --- | ---: |
| MAE | 1882.137589 MW |
| WAPE | 16.696600% |
| Bias | +1495.774468 MW |
| Bias relative to actual wind | +13.269140% |
| Actual wind below forecast | 77.446809% of matched targets |
| P90 absolute miss | 4013.4 MW |

The default forecast's latest and previous publications have identical generation values. Its comparison correctly reports 0 MW / 0% change; the two lines overlap. Tests also cover non-zero revisions, missing comparisons, zero baselines and later ineligible publications.

Earlier verification also covers an uncached early-January import, January/February boundaries, London clock changes, and request-failure recovery without showing another selection's results. See [methods](METHODOLOGY.md) for the exact evaluation window, alignment convention and interpretation limits.
