# Calculations and interpretation

## Assignment boundary

GridBricks supports two assignment requirements: understand the wind forecast available at a purchase decision time, and quantify earlier forecast error. Inputs are national Elexon **WINDFOR** forecasts and **FUELHH WIND** actual generation only. The January 2026 demonstration is a date range, not a hard-coded application limit.

There is no customer-demand input or client supply position in the provided data. A national generation forecast is not the utility's contracted wind entitlement. The dashboard therefore supplies forecast evidence rather than an electricity purchase quantity.

A portfolio buying calculation would need a demand forecast per delivery period, existing purchases, attributable generation, and agreed treatment of losses, uncertainty, prices and trading constraints. Those inputs and trading decisions remain outside this build. More national forecast-error metrics cannot fill that gap.

## Decision time and forecast selection

For decision date D and London clock time T:

1. Convert D/T to an unambiguous UTC cutoff.
2. Forecast the following London delivery day, D+1.
3. At each native source target, select the latest non-conflicted forecast published at or before the cutoff.
4. For comparison, select the preceding eligible version for that same target. A previous version is not necessarily the same publication across every target; each tooltip and CSV row gives its publication time.

Later publications do not change this selection. Application receipt timestamps are retained for auditing, but replay uses source publication time. A late import does not prove when a particular client originally received that publication.

The previous line is dashed violet. The selected line is cyan. Missing comparisons stay missing rather than becoming zero or borrowing a later forecast.

```text
revision MW = selected forecast − previous forecast
revision % = revision MW ÷ |previous forecast| × 100
```

Positive means wind was revised upward; negative means less wind is now forecast. A zero previous forecast makes revision % unavailable while the MW change remains valid. The highlighted biggest change has the largest absolute MW revision among comparable targets; it preserves the signed value and delivery time. This is a revision to the same target, not the change in wind between adjacent hours.

## The evaluation window

For selected decision date D, evaluate the earlier decision dates **D−30 through D−1**, each at the same chosen London clock time. Each earlier decision forecasts its next day. Actual observations are eligible only when:

- Their half-hour period has finished by the overall selected moment.
- Their source publication time is no later than that moment.
- The record is not marked conflicted.

If several actual revisions exist, select the latest eligible version. No later forecast or actual revision can influence an earlier cutoff.

For **27 January 2026, 09:00**, earlier decisions run from **28 December through 26 January**. Delivery evidence starts on 29 December and ends with the completed eligible targets on 27 January. At hourly forecast resolution, the expected target count is **29 × 24 + 9 = 705**, not 720. Future unfinished periods do not count against coverage. A finished period with missing or not-yet-published actual data does count as incomplete evidence.

## Source alignment and units

January WINDFOR targets are hourly. FUELHH actuals are half-hourly. Match exact `startTime`: an hourly forecast target is compared with the FUELHH half-hour beginning at that timestamp. This is the application's explicit comparison convention; it is not a manufactured extra forecast or an average of both half-hours. Both values are reported in MW.

Source resolution is retained, including genuine half-hour forecast targets where supplied. Missing observations remain null/gaps. Metrics use only matched eligible targets; forecast summaries use available forecast targets. The charts do not connect through missing values.

MW is power; MWh is energy over a duration. Multiplying power by the duration gives energy when that power represents the period: 100 MW sustained for 0.5 hours equals 50 MWh. Do not treat the point comparison or the 30-day sum of errors as a client energy purchase volume.

## Metrics

Let `e = forecast − actual` for each of n matched targets, and `A = Σ |actual|` over those same targets.

| Field | Formula | Interpretation |
| --- | --- | --- |
| MAE | `Σ |e| / n` | Average miss size, MW |
| Bias | `Σ e / n` | Positive means actual wind was generally below forecast; negative means above |
| WAPE | `Σ |e| / A × 100` | Aggregate absolute miss relative to actual wind, % |
| Bias % | `Σ e / A × 100` | Directional aggregate miss relative to actual wind, % |
| Coverage | `n / expected completed targets × 100` | Evidence completeness, not accuracy |
| Wind below forecast | `count(e > 0) / n × 100` | Historical frequency of actual wind being below forecast |
| P90 absolute miss | 90th percentile of `|e|`, NumPy linear interpolation | A larger historical miss scale, MW |
| RMSE | `sqrt(Σ e² / n)` | Emphasises larger misses; retained in API and saved JSON |

For example, forecasts of **120, 60, 200 MW** and actuals of **100, 100, 100 MW** give errors **+20, −40, +100 MW**. MAE is **53.3 MW**, WAPE **53.3%**, bias **+26.7 MW**, bias % **+26.7%**, below-forecast frequency **66.7%**, and P90 absolute miss **88 MW**. This example illustrates arithmetic; it is not the January result.

WAPE avoids dividing each target's error by a potentially tiny actual value. It can exceed 100%. Do not present `100 − WAPE` as accuracy or confuse it with the share of forecasts that were correct. When A is zero, WAPE and bias % are unavailable. With no matches, all error metrics are unavailable. Zero actuals still count as valid matches and contribute to MAE, P90 and historical frequency.

## What the metrics cannot promise

The 30-day sample describes past national wind outcomes under the selected decision policy. Weather regimes, seasonality and forecast horizons can change. Adjacent errors can be correlated, and a short window may miss rare events. P90 is a descriptive percentile, not a calibrated prediction interval. The below-forecast rate is not tomorrow's shortfall probability.

A positive bias does not justify buying that many MW for one utility. National wind error must not be substituted for the client's own renewable exposure. The product deliberately avoids a buy recommendation or an artificial risk buffer derived from these statistics alone.

## London clock changes

Store timestamps in UTC and derive delivery-day boundaries in Europe/London. A day can have 23, 24 or 25 hours; never assume 48 half-hours universally. The chosen user decision time must be real and unambiguous; invalid spring-gap or repeated autumn times receive a validation message.

For the earlier daily evaluation policy, a repeated clock time uses its first occurrence and a skipped clock time moves forward by the clock-change gap. That deterministic convention lets a valid selected decision evaluate a window crossing a clock change.

## Imports and freshness

The demonstration import includes December so early-January decisions have preceding history. Other uncached selections queue missing days using the same durable ingestion code. Completed imports are reused, jobs are coalesced and retries preserve old data.

The source line separates forecast publication from the last successful upstream check. A successful check does not imply a new publication. Loading, missing-data and stale-source messages explain limits on the available results without exposing queue controls on the dashboard.

## Saved evidence and exports

New reports use method **decision-dashboard-v3**. Their fingerprints include cutoff, selected records, comparison versions, values and calculation outputs, and exclude volatile import/freshness clocks. A changed source set requires refreshing the visible report before exporting.

CSV is generated from a saved report, not a fresh independent calculation. Forecast rows include `previous_mw`, `previous_publish_time`, `previous_id`, `revision_mw` and `revision_percent`. Evaluation rows include source IDs, publication times and signed errors. Its `window_*` percentage/P90 columns repeat the aggregate metadata for the entire evaluation window; they are not per-row percentages. JSON export includes the complete frozen report and metrics.

Existing stored analyses retain their own method, results and CSV schema. Adding new dashboard metrics does not rewrite earlier saved evidence.
