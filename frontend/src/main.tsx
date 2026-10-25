import {
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  Clock3,
  Download,
  LoaderCircle,
  TriangleAlert,
  Wind,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  API_BASE,
  selectionQuery,
  type Dashboard,
  type EvaluationReport,
  type ForecastReport,
  type Selection,
} from "./api";
import { WindChart } from "./charts";
import "./styles.css";

const initialSelection: Selection = {
  decision_date: "2026-01-27",
  decision_time: "09:00",
};
const number = (n: number | null | undefined, digits = 0) =>
  n == null
    ? "—"
    : n.toLocaleString("en-GB", { maximumFractionDigits: digits });
const londonDay = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const londonStamp = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const dateLabel = (v: string) => londonDay.format(new Date(`${v}T12:00:00Z`));
const stampLabel = (v: string | null | undefined) =>
  v ? londonStamp.format(new Date(v)) : "Not available";
const today = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/London",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
type Tab = "forecast" | "evaluation";

function Metric({
  label,
  value,
  unit,
  detail,
  accent = false,
}: {
  label: string;
  value: string;
  unit?: string;
  detail: string;
  accent?: boolean;
}) {
  return (
    <div className="metric">
      <p className="metric-label">{label}</p>
      <p className={`metric-value${accent ? " accent" : ""}`}>
        {value}
        {unit && <span>{unit}</span>}
      </p>
      <p className="metric-detail">{detail}</p>
    </div>
  );
}

function Empty({
  loading,
  children,
}: {
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="empty-chart" role="status">
      {loading ? (
        <LoaderCircle size={28} className="spin" />
      ) : (
        <Wind size={30} />
      )}
      <p>{children}</p>
    </div>
  );
}

function ForecastPanel({
  report,
  importing,
}: {
  report: ForecastReport;
  importing: boolean;
}) {
  return (
    <>
      <div className="report-heading">
        <div>
          <p className="section-label">NEXT-DAY OUTLOOK</p>
          <h1>Forecast for {dateLabel(report.delivery_date)}</h1>
          <p>Available at {stampLabel(report.as_of)} · London time</p>
        </div>
      </div>
      <div className="metrics">
        <Metric
          label="Average expected wind"
          value={number(report.summary.average_mw)}
          unit="MW"
          detail="Across the available forecast periods"
          accent
        />
        <Metric
          label="Lowest expected wind"
          value={number(report.summary.minimum?.forecast_mw)}
          unit="MW"
          detail={
            report.summary.minimum
              ? `At ${report.summary.minimum.local_time}`
              : "No forecast available"
          }
        />
        <Metric
          label="Highest expected wind"
          value={number(report.summary.maximum?.forecast_mw)}
          unit="MW"
          detail={
            report.summary.maximum
              ? `At ${report.summary.maximum.local_time}`
              : "No forecast available"
          }
        />
      </div>
      <section className="chart-card">
        <div className="chart-heading">
          <div>
            <h2>Expected wind generation</h2>
            <p>
              How wind output is expected to change through the delivery day.
            </p>
          </div>
          <span className="chart-legend">
            <i className="cyan" />
            Forecast
          </span>
        </div>
        {report.summary.forecast_count ? (
          <WindChart points={report.points} />
        ) : (
          <Empty loading={importing}>
            {importing
              ? "Loading forecast records for this date…"
              : "No forecast is available for this decision time."}
          </Empty>
        )}
        <div className="chart-caption">
          <span>London time · Power output in MW</span>
          <span>
            {report.summary.forecast_count} of {report.summary.expected_count}{" "}
            forecast periods available
          </span>
        </div>
      </section>
    </>
  );
}

function EvaluationPanel({
  report,
  importing,
}: {
  report: EvaluationReport;
  importing: boolean;
}) {
  const { metrics } = report;
  const bias = metrics.bias;
  const tendency =
    bias == null
      ? "No matched outcomes available"
      : bias === 0
        ? "No consistent difference from actual wind"
        : `Actual wind averaged ${bias > 0 ? "below" : "above"} forecast`;
  return (
    <>
      <div className="report-heading">
        <div>
          <p className="section-label">EARLIER FORECAST PERFORMANCE</p>
          <h1>Evaluation of the previous 30 days</h1>
          <p>
            Only outcomes available by {stampLabel(report.as_of)} · London time
          </p>
        </div>
      </div>
      <div className="metrics">
        <Metric
          label="Average forecast miss"
          value={number(metrics.mae)}
          unit="MW"
          detail="Average size of the forecast error"
          accent
        />
        <Metric
          label="Forecast tendency"
          value={number(bias == null ? null : Math.abs(bias))}
          unit="MW"
          detail={tendency}
        />
        <Metric
          label="Periods evaluated"
          value={number(metrics.matched)}
          unit="periods"
          detail={`${number(metrics.coverage, 1)}% of ${number(metrics.expected)} completed periods`}
        />
      </div>
      <section className="chart-card">
        <div className="chart-heading">
          <div>
            <h2>Forecast versus actual wind</h2>
            <p>
              Earlier day-ahead forecasts compared with what was known to have
              happened.
            </p>
          </div>
          <div className="legends">
            <span className="chart-legend">
              <i className="cyan" />
              Forecast
            </span>
            <span className="chart-legend">
              <i className="violet" />
              Actual wind
            </span>
          </div>
        </div>
        {metrics.matched ? (
          <WindChart points={report.points} evaluation />
        ) : (
          <Empty loading={importing}>
            {importing
              ? "Loading earlier forecasts and actual generation…"
              : "There are no matched outcomes available before this decision time."}
          </Empty>
        )}
        <div className="chart-caption">
          <span>London time · Power output in MW</span>
          <span>Gaps mean data is unavailable</span>
        </div>
      </section>
    </>
  );
}

function App() {
  const [draft, setDraft] = useState<Selection>(initialSelection);
  const [applied, setApplied] = useState<Selection>(initialSelection);
  const [tab, setTab] = useState<Tab>("forecast");
  const [exporting, setExporting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [notification, setNotification] = useState("");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const query = useQuery({
    queryKey: ["dashboard", applied.decision_date, applied.decision_time],
    queryFn: ({ signal }) =>
      api<Dashboard>(`/api/dashboard?${selectionQuery(applied)}`, { signal }),
    refetchInterval: 30000,
    retry: 1,
  });
  const data = query.data;
  const report = data
    ? tab === "forecast"
      ? data.forecast
      : data.evaluation
    : undefined;
  const importing = data?.history.state === "loading";
  const sameSelection =
    draft.decision_date === applied.decision_date &&
    draft.decision_time === applied.decision_time;
  const hasValues =
    report?.kind === "forecast"
      ? report.summary.forecast_count > 0
      : !!report?.metrics.matched;

  async function viewResults(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotification("");
    if (!sameSelection) {
      setApplied({ ...draft });
      return;
    }
    if (data?.history.failed_days) {
      setRetrying(true);
      try {
        await api(`/api/refresh?${selectionQuery(applied)}`, {
          method: "POST",
        });
      } catch (error) {
        setNotification((error as Error).message);
      } finally {
        setRetrying(false);
      }
    }
    await query.refetch();
  }
  function tabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next =
      event.key === "ArrowRight" || event.key === "ArrowLeft"
        ? 1 - index
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? 1
            : null;
    if (next === null) return;
    event.preventDefault();
    setTab(next === 0 ? "forecast" : "evaluation");
    tabs.current[next]?.focus();
  }
  async function download() {
    if (!report) return;
    setExporting(true);
    setNotification("");
    const selection = {
      decision_date: report.decision_date,
      decision_time: report.decision_time,
    };
    try {
      const saved = await api<{ id: string }>("/api/analysis-runs", {
        method: "POST",
        body: JSON.stringify({
          dashboard: true,
          kind: report.kind,
          parameters: selection,
          expected_fingerprint: report.fingerprint,
        }),
      });
      const response = await fetch(`${API_BASE}/api/export?run_id=${saved.id}`);
      if (!response.ok)
        throw new Error("The CSV could not be downloaded. Please try again.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `gridbricks-${report.kind === "accuracy" ? "evaluation" : "forecast"}-${selection.decision_date}-${selection.decision_time.replace(":", "")}.csv`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotification("CSV downloaded.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setNotification(
          "New source data arrived. Please download the updated results again.",
        );
        await query.refetch();
      } else setNotification((error as Error).message);
    } finally {
      setExporting(false);
    }
  }
  const missing =
    report?.kind === "forecast"
      ? report.summary.forecast_count < report.summary.expected_count
      : report
        ? report.metrics.matched < report.metrics.expected
        : false;
  const warning = data?.history.failed_days
    ? "Some source records could not be loaded. Use View results to retry."
    : importing
      ? "Loading source records. Results may be incomplete while this finishes."
      : data?.source.source_issue
        ? "There is a source update issue. Showing the last stored data."
        : data?.source.stale
          ? "The source check is overdue. Showing the latest stored data."
          : missing
            ? "Some periods have missing data. Only available records are used."
            : "";

  return (
    <div className="application">
      <header className="topbar">
        <div className="header-inner">
          <a href="/" className="brand" aria-label="GridBricks home">
            <span className="brand-symbol" aria-hidden="true">
              <i />
              <i />
              <i />
              <i />
            </span>
            GridBricks<span className="brand-dot">.</span>
          </a>
          <nav role="tablist" aria-label="Reports">
            {(["forecast", "evaluation"] as const).map((name, index) => (
              <button
                ref={(element) => {
                  tabs.current[index] = element;
                }}
                key={name}
                type="button"
                role="tab"
                id={`tab-${name}`}
                aria-selected={tab === name}
                aria-controls={`panel-${name}`}
                tabIndex={tab === name ? 0 : -1}
                onClick={() => setTab(name)}
                onKeyDown={(event) => tabKey(event, index)}
              >
                {name === "forecast" ? "Forecast" : "Evaluation"}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="main-shell">
        <form
          className="selection-form"
          onSubmit={viewResults}
          aria-label="Decision date and time"
        >
          <div className="selection-fields">
            <label>
              <span>Decision date</span>
              <div className="input-wrap">
                <CalendarDays size={17} aria-hidden="true" />
                <input
                  required
                  aria-label="Decision date"
                  type="date"
                  max={today()}
                  value={draft.decision_date}
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((previous) => ({
                      ...previous,
                      decision_date: value,
                    }));
                  }}
                />
              </div>
            </label>
            <label>
              <span>Decision time</span>
              <div className="input-wrap">
                <Clock3 size={17} aria-hidden="true" />
                <input
                  required
                  aria-label="Decision time"
                  type="time"
                  step="60"
                  value={draft.decision_time}
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((previous) => ({
                      ...previous,
                      decision_time: value,
                    }));
                  }}
                />
              </div>
            </label>
            <span className="timezone">London time</span>
          </div>
          <button className="view-button" type="submit" disabled={retrying}>
            {retrying || (query.isFetching && sameSelection) ? (
              <LoaderCircle size={17} className="spin" aria-hidden="true" />
            ) : null}
            View results <ArrowRight size={17} aria-hidden="true" />
          </button>
        </form>
        <div
          role="tabpanel"
          id={`panel-${tab}`}
          aria-labelledby={`tab-${tab}`}
          aria-busy={query.isPending}
          tabIndex={0}
        >
          {query.isError ? (
            <div className="request-error" role="alert">
              <TriangleAlert size={24} />
              <h1>We couldn’t load these results.</h1>
              <p>
                {query.error instanceof TypeError
                  ? "Please check your connection and try View results again."
                  : query.error.message}
              </p>
            </div>
          ) : data ? (
            <>
              {tab === "forecast" ? (
                <ForecastPanel report={data.forecast} importing={importing} />
              ) : (
                <EvaluationPanel
                  report={data.evaluation}
                  importing={importing}
                />
              )}
              <div className="source-row">
                <div className="source-details">
                  <a
                    href="https://bmrs.elexon.co.uk/wind-generation"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Elexon <ArrowUpRight size={12} />
                  </a>
                  <span className="separator" />
                  <span>
                    Latest forecast publication:{" "}
                    {stampLabel(
                      report?.kind === "forecast"
                        ? report.summary.latest_publication
                        : report?.latest_publication,
                    )}
                  </span>
                  <span className="separator" />
                  <span>
                    Last checked: {stampLabel(data.source.last_checked)}
                  </span>
                </div>
                <button
                  className="download-button"
                  onClick={download}
                  disabled={exporting || !hasValues}
                >
                  {exporting ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : (
                    <Download size={15} />
                  )}
                  Download CSV
                </button>
              </div>
              {warning && (
                <p className="data-warning" role="status">
                  {importing ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : (
                    <TriangleAlert size={15} />
                  )}
                  {warning}
                </p>
              )}
            </>
          ) : (
            <div className="loading-report" role="status">
              <div className="skeleton-heading" />
              <div className="metrics">
                {[0, 1, 2].map((n) => (
                  <div className="metric skeleton" key={n} />
                ))}
              </div>
              <div className="chart-card">
                <Empty loading>
                  Loading results for {dateLabel(applied.decision_date)} at{" "}
                  {applied.decision_time}…
                </Empty>
              </div>
            </div>
          )}
        </div>
        <div
          hidden
          role="tabpanel"
          id={`panel-${tab === "forecast" ? "evaluation" : "forecast"}`}
          aria-labelledby={`tab-${tab === "forecast" ? "evaluation" : "forecast"}`}
        />
        {notification && (
          <div className="notification" role="status">
            <Check size={16} />
            <span>{notification}</span>
            <button
              aria-label="Dismiss message"
              onClick={() => setNotification("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15000, refetchOnWindowFocus: true } },
});
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>,
);
