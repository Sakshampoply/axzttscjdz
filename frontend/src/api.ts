export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `The server returned ${response.status}. Please try again.`);
  }
  return response.json();
}

export function queryString(values: Record<string, unknown>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value));
  });
  return params.toString();
}

export interface Point {
  start_time: string; local_time: string; forecast_mw: number | null; previous_mw: number | null;
  revision_mw: number | null; actual_mw: number | null; error_mw: number | null;
  forecast_publish_time: string | null; previous_publish_time: string | null; actual_publish_time: string | null;
  forecast_id: number | null; actual_id: number | null; status?: string;
}
export interface Metrics { mae: number | null; bias: number | null; rmse: number | null; wape: number | null; matched: number; expected: number; coverage: number | null; }
export interface Insight { title: string; text: string; kind?: string; }
export interface Forecast {
  kind: 'forecast'; mode: string; decision_date: string; delivery_date: string; decision_time: string;
  as_of: string; evaluation_at: string; availability: string; reveal_actuals: boolean; compare_publication: string | null;
  native_resolution_minutes: number; points: Point[]; fingerprint: string; alignment: string; method_version: string;
  actual_curve: { start_time: string; generation_mw: number }[]; publications: string[]; insights: Insight[]; metrics: Metrics;
  summary: { minimum: Point | null; maximum: Point | null; largest_downward_revision: Point | null;
    forecast_count: number; expected_count: number; forecast_coverage: number; average_mw: number | null;
    latest_publication: string | null; oldest_publication: string | null; };
}
export interface Accuracy {
  kind: 'accuracy'; start: string; end: string; decision_time: string; basis: string; known_at: string | null;
  evaluation_at: string; availability: string; fingerprint: string; metrics: Metrics; points: Point[];
  daily: (Metrics & { decision_date: string; delivery_date: string })[];
  histogram: { from_mw: number; to_mw: number; count: number }[];
  represented_days: number; insights: Insight[]; alignment: string;
  worst_day: (Metrics & { delivery_date: string }) | null;
}
export interface Job { id: number; kind: string; status: string; error: string | null; attempts: number; }
export interface DataQuality {
  checked_at: string; sync_interval_seconds: number; failed_jobs: number; jobs: Job[];
  datasets: { dataset: string; records: number; first_target: string | null; latest_target: string | null;
    latest_publication: string | null; last_checked: string | null; stale: boolean; error: string | null; retry_after: string | null }[];
}
