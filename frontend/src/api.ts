export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const message =
      typeof error.detail === "string"
        ? error.detail
        : response.status === 422
          ? "Please check the decision date and time."
          : "The data service is unavailable. Please try again shortly.";
    throw new ApiError(message, response.status);
  }
  return response.json();
}

export interface Selection {
  decision_date: string;
  decision_time: string;
}
export function selectionQuery(selection: Selection) {
  return new URLSearchParams({ ...selection }).toString();
}
export interface ForecastPoint {
  start_time: string;
  local_time: string;
  forecast_mw: number | null;
  forecast_publish_time: string | null;
  forecast_id: number | null;
}
export interface EvaluationPoint extends ForecastPoint {
  decision_date: string;
  delivery_date: string;
  actual_mw: number | null;
  error_mw: number | null;
  actual_publish_time: string | null;
  actual_id: number | null;
}
export interface ForecastComparisonPoint extends ForecastPoint {
  previous_mw: number | null;
  previous_publish_time: string | null;
  previous_id: number | null;
  revision_mw: number | null;
  revision_percent: number | null;
}
export interface Report extends Selection {
  as_of: string;
  fingerprint: string;
  method_version: string;
}
export interface ForecastReport extends Report {
  kind: "forecast";
  delivery_date: string;
  native_resolution_minutes: number;
  points: ForecastComparisonPoint[];
  summary: {
    average_mw: number | null;
    minimum: ForecastPoint | null;
    maximum: ForecastPoint | null;
    forecast_count: number;
    expected_count: number;
    coverage: number;
    latest_publication: string | null;
    comparison_count: number;
    largest_revision: ForecastComparisonPoint | null;
  };
}
export interface EvaluationReport extends Report {
  kind: "accuracy";
  window_start: string;
  window_end: string;
  lookback_days: number;
  points: EvaluationPoint[];
  latest_publication: string | null;
  metrics: {
    mae: number | null;
    bias: number | null;
    rmse: number | null;
    wape: number | null;
    matched: number;
    expected: number;
    coverage: number | null;
    bias_percent: number | null;
    below_forecast_percent: number | null;
    p90_absolute_error_mw: number | null;
  };
}
export interface Dashboard {
  selection: Selection & { decision_at: string };
  forecast: ForecastReport;
  evaluation: EvaluationReport;
  source: {
    last_checked: string | null;
    stale: boolean;
    source_issue: boolean;
  };
  history: {
    state: "loading" | "ready" | "unavailable";
    pending_days: number;
    failed_days: number;
  };
}
