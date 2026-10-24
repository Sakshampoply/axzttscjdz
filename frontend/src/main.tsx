import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, BookOpen, CalendarDays, CheckCircle2, ChevronDown, Clock3, Database, Download, ExternalLink, FileText, History, Info, Layers3, LineChart, LoaderCircle, Radio, RefreshCw, ShieldCheck, TrendingDown, Wind, X } from 'lucide-react';
import { api, API_BASE, queryString, type Accuracy, type DataQuality, type Forecast, type Job } from './api';
import { DailyChart, ForecastChart, HeatmapChartView, HistogramChart, RevisionsChart, shortDate } from './charts';
import './styles.css';

const number = (n: number | null | undefined, digits = 0) => n === null || n === undefined ? '—' : n.toLocaleString('en-GB', { maximumFractionDigits: digits });
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const addDays = (day: string, n: number) => new Date(Date.parse(`${day}T12:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
const longDate = (day: string) => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(`${day}T12:00:00Z`));
const dateTime = (v: string | null | undefined) => v ? new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(new Date(v)) : 'Not available';
const age = (v: string | null | undefined) => {
  if (!v) return 'Not checked yet';
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(v)) / 1000));
  return seconds < 60 ? 'Just now' : seconds < 3600 ? `${Math.floor(seconds / 60)} min ago` : `${Math.floor(seconds / 3600)} hr ago`;
};

function Logo() { return <a className="brand" href="/" aria-label="GridBricks home"><span className="brand-symbol"><i /><i /><i /><i /></span><span>GridBricks<span className="brand-period">.</span></span></a>; }

function App() {
  const client = useQueryClient();
  const [tab, setTab] = useState<'forecast' | 'accuracy' | 'method'>('forecast');
  const [mode, setMode] = useState<'current' | 'replay'>('current');
  const [decisionDate, setDecisionDate] = useState(today());
  const [decisionTime, setDecisionTime] = useState('09:00');
  const [availability, setAvailability] = useState('published');
  const [reveal, setReveal] = useState(false);
  const [comparison, setComparison] = useState('');
  const [rangeStart, setRangeStart] = useState(addDays(today(), -30));
  const [rangeEnd, setRangeEnd] = useState(addDays(today(), -1));
  const [basis, setBasis] = useState('retrospective');
  const [qualityOpen, setQualityOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [toast, setToast] = useState('');
  const [tableOpen, setTableOpen] = useState(false);

  const forecastParams = { mode, decision_date: mode === 'replay' ? decisionDate : undefined, decision_time: decisionTime, availability, reveal_actuals: reveal, compare_publication: comparison || undefined };
  const forecastQuery = useQuery({ queryKey: ['forecast', forecastParams], queryFn: () => api<Forecast>(`/api/forecast?${queryString(forecastParams)}`), refetchInterval: 30000, retry: 1 });
  const data = forecastQuery.data;
  const quality = useQuery({ queryKey: ['quality'], queryFn: () => api<DataQuality>('/api/data-quality'), refetchInterval: 30000, retry: 1 });
  const selectedDate = data?.decision_date || decisionDate;
  const recentParams = { start: addDays(selectedDate, -30), end: addDays(selectedDate, -1), decision_time: decisionTime,
    basis: 'known', known_at: data?.as_of, availability };
  const recent = useQuery({ queryKey: ['recent', recentParams], queryFn: () => api<Accuracy>(`/api/accuracy?${queryString(recentParams)}`), enabled: !!data, refetchInterval: 30000, retry: 1 });
  const accuracyParams = { start: rangeStart, end: rangeEnd, decision_time: decisionTime, basis, known_at: basis === 'known' ? data?.as_of : undefined, availability };
  const accuracy = useQuery({ queryKey: ['accuracy', accuracyParams], queryFn: () => api<Accuracy>(`/api/accuracy?${queryString(accuracyParams)}`), enabled: tab === 'accuracy' && !!data, refetchInterval: 30000, retry: 1 });
  const stale = quality.data?.datasets.some(d => d.stale || d.error) ?? true;
  const syncing = quality.data?.jobs.some(j => j.kind === 'refresh') || refreshing;

  function notify(message: string) { setToast(message); window.setTimeout(() => setToast(''), 6500); }
  function demo() {
    setMode('replay'); setDecisionDate('2026-01-27'); setDecisionTime('09:00'); setAvailability('published');
    setReveal(false); setComparison(''); setRangeStart('2026-01-01'); setRangeEnd('2026-01-31'); setBasis('retrospective');
  }
  async function refresh() {
    setRefreshing(true);
    try {
      const job = await api<Job>('/api/refresh', { method: 'POST' });
      notify(job.status === 'completed' ? 'The source was checked recently. Showing the latest stored records.' : 'Update requested. Existing results stay available while the worker checks Elexon.');
      await client.invalidateQueries({ queryKey: ['quality'] });
      await client.invalidateQueries({ queryKey: ['forecast'] });
    } catch (e) { notify((e as Error).message); }
    finally { setRefreshing(false); }
  }
  async function exportData() {
    const result = tab === 'accuracy' ? accuracy.data : data;
    if (!result) return;
    setExporting(true);
    const parameters = result.kind === 'forecast' ? {
      mode: result.mode, decision_date: result.decision_date, decision_time: result.decision_time,
      availability: result.availability, reveal_actuals: result.reveal_actuals, compare_publication: result.compare_publication,
      as_of: result.as_of, evaluation_at: result.evaluation_at,
    } : { start: result.start, end: result.end, decision_time: result.decision_time, basis: result.basis,
      known_at: result.known_at, evaluation_at: result.evaluation_at, availability: result.availability };
    try {
      const snapshot = await api<{ id: string }>('/api/analysis-runs', { method: 'POST', body: JSON.stringify({ kind: result.kind, parameters, expected_fingerprint: result.fingerprint }) });
      const response = await fetch(`${API_BASE}/api/export?run_id=${snapshot.id}`);
      if (!response.ok) throw new Error('Export failed. Please try again.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = `gridbricks-${result.kind}-${snapshot.id.slice(0, 8)}.csv`; link.click(); URL.revokeObjectURL(url);
      notify('CSV downloaded with its calculation snapshot and source references.');
    } catch (e) { notify((e as Error).message); }
    finally { setExporting(false); }
  }

  return <div className="application">
    <header className="topbar"><div className="topbar-inner"><Logo /><div className="workspace-label"><span /> Wind intelligence <ChevronDown size={13} /></div>
      <nav aria-label="Main navigation">{[
        ['forecast', 'Forecast', <LineChart size={16} />], ['accuracy', 'Accuracy', <Activity size={16} />], ['method', 'How it works', <BookOpen size={16} />],
      ].map(([key, label, icon]) => <button key={String(key)} className={tab === key ? 'nav-link active' : 'nav-link'} onClick={() => setTab(key as typeof tab)}>{icon}{label}</button>)}</nav>
      <div className="topbar-end"><span className="market-badge">GB</span><span>Great Britain</span><span className="avatar" title="Public read-only workspace">W</span></div>
    </div></header>

    <main className="main-shell">
      <div className="page-heading"><div><div className="eyebrow"><span className="tiny-line" /> WIND GENERATION INTELLIGENCE</div>
        <h1>{tab === 'forecast' ? 'Tomorrow, in focus.' : tab === 'accuracy' ? 'Know the forecast. Know its limits.' : 'A clear view of the numbers.'}</h1>
        <p>{tab === 'forecast' ? 'Understand the forecast, follow the changes, and make a more informed decision.' : tab === 'accuracy' ? 'Measure how decision-time forecasts performed against actual wind generation.' : 'Where the data comes from, what we calculate, and what the results mean.'}</p>
      </div><div className="heading-actions"><button className="button ghost" onClick={() => window.print()}><FileText size={15} /> Print assessment</button><button className="button" onClick={exportData} disabled={!data || exporting || tab === 'method'}>{exporting ? <LoaderCircle size={15} className="spin" /> : <Download size={15} />} Export CSV</button></div></div>

      <section className="control-panel" aria-label="Analysis controls"><div className="control-main"><div className="segmented mode-switch"><button className={mode === 'current' ? 'selected' : ''} onClick={() => { setMode('current'); setComparison(''); setAvailability('published'); setReveal(false); }}><Radio size={14} /> Current</button><button className={mode === 'replay' ? 'selected' : ''} onClick={() => { setMode('replay'); setComparison(''); }}><History size={14} /> Historical replay</button></div>
        <div className="control-divider" /><label className="field-label"><CalendarDays size={15} /><span>Decision date</span><input aria-label="Decision date" type="date" max={today()} value={mode === 'current' ? selectedDate : decisionDate} disabled={mode === 'current'} onChange={e => { setDecisionDate(e.target.value); setComparison(''); }} /></label>
        <label className="field-label"><Clock3 size={15} /><span>{mode === 'current' ? 'View' : 'Decision time'}</span>{mode === 'current' ? <strong>Latest available</strong> : <input aria-label="Decision time" type="time" value={decisionTime} onChange={e => { setDecisionTime(e.target.value); setComparison(''); }} />}</label>
      </div><div className="control-secondary"><span className="timezone">Europe/London</span><button className="demo-preset" onClick={demo}><Layers3 size={14} /> January 2026 <ArrowUpRight size={13} /></button></div></section>

      <div className="context-row"><div><span className="context-icon"><Wind size={14} /></span> Delivery: <strong>{data ? longDate(data.delivery_date) : 'Loading delivery day…'}</strong><span className="context-dot">·</span><span>{mode === 'current' ? 'Latest source publications' : `Forecasts available before ${decisionTime} London time`}</span></div><button className={`sync-status ${stale ? 'is-stale' : ''}`} onClick={() => setQualityOpen(true)}><span className={`status-dot ${syncing ? 'pulse' : ''}`} />{syncing ? 'Checking for updates' : stale ? 'Review data freshness' : 'Source checks up to date'}<Info size={13} /></button></div>

      {forecastQuery.error && <div className="notice error"><Info size={17} /><div><strong>We couldn’t load this analysis.</strong><p>{forecastQuery.error.message}</p></div><button onClick={() => forecastQuery.refetch()}>Try again</button></div>}
      {mode === 'replay' && availability === 'received' && <div className="notice"><ShieldCheck size={17} /><div><strong>Application receipt replay</strong><p>Only records this application had received by the selected cutoff are eligible. Backfilled January records will not appear as if received in January.</p></div></div>}

      {tab === 'forecast' && <>
        <div className="metric-grid"><Metric label="Average forecast wind" value={number(data?.summary.average_mw)} unit="MW" icon={<Wind size={19} />} foot="Across available native targets" />
          <Metric label="Lowest expected wind" value={number(data?.summary.minimum?.forecast_mw)} unit="MW" icon={<TrendingDown size={19} />} foot={data?.summary.minimum ? `At ${data.summary.minimum.local_time}` : 'Awaiting forecast records'} />
          <Metric label="Recent average miss" value={number(recent.data?.metrics.mae)} unit="MW" icon={<Activity size={19} />} foot={recent.data?.metrics.matched ? `${number(recent.data.metrics.matched)} earlier matched targets · ${decisionTime} policy` : 'Insufficient eligible earlier history'} tooltip="MAE: the average absolute forecast error on prior delivery targets, using only actuals known by this view’s information cutoff." />
          <Metric label="Forecast coverage" value={number(data?.summary.forecast_coverage)} unit="%" icon={<ShieldCheck size={19} />} foot={data ? `${data.summary.forecast_count} of ${data.summary.expected_count} native targets available` : 'Checking the selected day'} /></div>

        <div className="forecast-layout"><section className="card forecast-card"><div className="card-heading"><div><h2>Wind outlook <span className="small-tag">{data?.native_resolution_minutes || 60}-minute targets</span></h2><p>{data ? `${shortDate(data.delivery_date)} · Generation in megawatts (MW)` : 'Generation in megawatts (MW)'}</p></div><label className="toggle-label"><input type="checkbox" checked={reveal} onChange={e => setReveal(e.target.checked)} /><span className="toggle-track" /> Show what actually happened</label></div>
          <div className="publication-strip"><Clock3 size={12} /> Forecast published: <strong>{dateTime(data?.summary.latest_publication)}</strong>{data?.summary.oldest_publication !== data?.summary.latest_publication && <span>· Mixed publication times</span>}</div>
          {reveal && <div className="retrospective-note"><History size={13} /> Retrospective comparison. The selected forecast stays fixed to its information cutoff.</div>}
          <div className="chart-legend"><span><i className="legend-line blue" /> Selected forecast</span><span><i className="legend-line dashed" /> Earlier forecast</span>{reveal && <span><i className="legend-line green" /> Actual generation</span>}</div>
          {data?.summary.forecast_count ? <ForecastChart data={data} /> : <Empty loading={forecastQuery.isPending} title="No eligible forecast yet" text={availability === 'received' ? 'This application had not received records by that historical cutoff. Switch to source publication replay to reconstruct the published forecast.' : 'The worker may still be importing this date. Current forecasts are prioritised; historical data fills in separately.'} />}
          <div className="chart-footer"><span><Clock3 size={13} /> London time</span><span>{reveal ? `${data?.metrics.matched || 0} matched outcomes` : 'Actual outcomes remain hidden'}<span className="mini-divider" />Source: Elexon</span></div>
        </section>

        <aside className="card brief-card"><div className="brief-icon"><Wind size={20} /></div><div className="eyebrow">YOUR DECISION BRIEF</div><h2>The periods worth<br />a closer look.</h2><p className="brief-intro">A few signals from the selected forecast. Always review them alongside your own demand and contracts.</p>
          {data?.insights.slice(0, 3).map((insight, index) => <div className="brief-insight" key={insight.title}><span className="insight-number">0{index + 1}</span><div><h3>{insight.title}</h3><p>{insight.text}</p></div></div>)}
          {!data?.insights.length && <p className="muted">Your brief will appear when eligible forecasts are available.</p>}
          <div className="brief-bottom"><ShieldCheck size={15} /><span>Calculated from source records.<br />No AI-generated forecasts.</span></div>
        </aside></div>

        <section className="card revisions-card"><div className="card-heading"><div><h2>What changed?</h2><p>Revisions to expected wind. A downward bar means less wind is now forecast.</p></div><label className="select-label">Compare with<select aria-label="Comparison publication" value={comparison} onChange={e => setComparison(e.target.value)}><option value="">Previous available forecast</option>{data?.publications.slice(1, 30).map(p => <option key={p} value={p}>{dateTime(p)}</option>)}</select></label></div>
          {data?.summary.forecast_count ? <RevisionsChart data={data} /> : <div className="small-empty">Forecast revisions will appear once two eligible versions are available.</div>}
        </section>

        <section className="card values-section"><button className="table-toggle" onClick={() => setTableOpen(!tableOpen)} aria-expanded={tableOpen}><span><Database size={16} /><strong>Explore the underlying values</strong><span className="muted">Source timestamps and matched records</span></span><ChevronDown size={17} className={tableOpen ? 'rotated' : ''} /></button>
          {tableOpen && <div className="table-scroll"><table><caption className="sr-only">Forecast and actual values in MW at native target timestamps.</caption><thead><tr><th>Delivery time</th><th>Forecast, MW</th><th>Published</th><th>Revision, MW</th><th>Actual, MW</th><th>Error, MW</th></tr></thead><tbody>{data?.points.map(p => <tr key={p.start_time}><td>{p.local_time}</td><td>{number(p.forecast_mw)}</td><td>{dateTime(p.forecast_publish_time)}</td><td className={p.revision_mw !== null && p.revision_mw < 0 ? 'negative-value' : ''}>{p.revision_mw !== null && p.revision_mw > 0 ? '+' : ''}{number(p.revision_mw)}</td><td>{p.actual_mw === null ? reveal ? 'Awaiting actual data' : 'Hidden' : number(p.actual_mw)}</td><td>{number(p.error_mw)}</td></tr>)}</tbody></table></div>}
        </section>
        <div className="evidence-strip"><Info size={15} /><p>{data?.alignment || 'Source forecasts and actuals are matched at their original timestamps.'} Wind intelligence supports your assessment; it does not calculate your purchase volume.</p><button onClick={() => setTab('method')}>Read methodology <ArrowRight size={14} /></button></div>
      </>}

      {tab === 'accuracy' && <>
        <section className="card accuracy-controls"><div><h2>Evaluate a decision policy</h2><p>Each delivery target uses its latest forecast before {decisionTime} on the previous day.</p></div><div className="range-fields"><label>First decision<input aria-label="First decision date" type="date" value={rangeStart} max={rangeEnd} onChange={e => setRangeStart(e.target.value)} /></label><label>Last decision<input aria-label="Last decision date" type="date" value={rangeEnd} min={rangeStart} max={today()} onChange={e => setRangeEnd(e.target.value)} /></label></div></section>
        <div className="accuracy-basis"><div className="segmented"><button className={basis === 'retrospective' ? 'selected' : ''} onClick={() => setBasis('retrospective')}>Retrospective evaluation</button><button className={basis === 'known' ? 'selected' : ''} onClick={() => setBasis('known')}>Known before this decision</button></div><p>{basis === 'retrospective' ? 'Includes actual outcomes available now. This is hindsight, not decision-time evidence.' : `Only outcomes published before ${dateTime(data?.as_of)} are eligible.`}</p></div>
        {accuracy.error && <div className="notice error"><Info size={16} />{accuracy.error.message}</div>}
        <div className="metric-grid"><Metric label="Average forecast miss" value={number(accuracy.data?.metrics.mae)} unit="MW" icon={<Activity size={19} />} foot="Mean absolute error · lower is better" /><Metric label="Forecast tendency" value={number(accuracy.data?.metrics.bias)} unit="MW" icon={<ArrowDownRight size={19} />} foot="Positive: wind was below forecast" /><Metric label="Large-error measure" value={number(accuracy.data?.metrics.rmse)} unit="MW" icon={<LineChart size={19} />} foot="RMSE · gives large misses more weight" /><Metric label="Scoring coverage" value={number(accuracy.data?.metrics.coverage)} unit="%" icon={<ShieldCheck size={19} />} foot={`${number(accuracy.data?.metrics.matched)} / ${number(accuracy.data?.metrics.expected)} expected targets`} /></div>
        {accuracy.data && accuracy.data.metrics.matched > 0 ? <>
          <div className="two-column"><section className="card"><div className="card-heading"><div><h2>Average miss by delivery day</h2><p>Typical forecast error, in MW</p></div><span className="small-tag">{accuracy.data.represented_days} days with evidence</span></div><DailyChart data={accuracy.data} /></section><section className="card"><div className="card-heading"><div><h2>Which way did forecasts miss?</h2><p>Negative: actual above forecast · Positive: actual below forecast</p></div></div><HistogramChart data={accuracy.data} /></section></div>
          <section className="card heatmap-card"><div className="card-heading"><div><h2>The pattern behind the average</h2><p>Signed error by delivery date and target time. Blank cells have no matched evidence.</p></div><span className="small-tag">MW</span></div><HeatmapChartView data={accuracy.data} /></section>
          <div className="accuracy-notes">{accuracy.data.insights.map(i => <div className="card insight-note" key={i.title}><Info size={18} /><div><h3>{i.title}</h3><p>{i.text}</p></div></div>)}<div className="card insight-note"><Activity size={18} /><div><h3>Relative error</h3><p>WAPE is {number(accuracy.data.metrics.wape, 1)}%. It compares total absolute error with total actual generation. It is not a “percent accurate” score.</p></div></div></div>
          <details className="card accuracy-records"><summary>Accessible accuracy data and source references</summary><div className="table-scroll"><table><caption className="sr-only">Every expected forecast target in the selected decision range</caption><thead><tr><th>Target, UTC</th><th>Forecast, MW</th><th>Actual, MW</th><th>Error, MW</th><th>Forecast ID</th><th>Actual ID</th></tr></thead><tbody>{accuracy.data.points.map(p => <tr key={p.start_time}><td>{p.start_time}</td><td>{number(p.forecast_mw)}</td><td>{number(p.actual_mw)}</td><td>{number(p.error_mw)}</td><td>{p.forecast_id ?? '—'}</td><td>{p.actual_id ?? '—'}</td></tr>)}</tbody></table></div></details>
        </> : <section className="card"><Empty loading={accuracy.isPending} title="No matched evidence for this view" text="The selected range may still be importing, or its outcomes were not yet available at the chosen information cutoff. Missing evidence is never treated as zero error." /></section>}
      </>}

      {tab === 'method' && <Methodology availability={availability} setAvailability={setAvailability} openQuality={() => setQualityOpen(true)} />}

      <footer className="footer"><div><span className="footer-mark"><Wind size={16} /></span><span>Built for a more informed tomorrow.</span></div><div><a href="https://bmrs.elexon.co.uk/wind-generation" target="_blank" rel="noreferrer">Data from Elexon <ExternalLink size={11} /></a><span>London time</span><button onClick={() => setQualityOpen(true)}>Data status <span className={`status-dot ${stale ? 'amber' : ''}`} /></button><button className="refresh-button" onClick={refresh} disabled={refreshing}><RefreshCw size={13} className={refreshing ? 'spin' : ''} /> Check for updates</button></div></footer>
    </main>

    {toast && <div role="status" className="toast"><CheckCircle2 size={17} /><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={15} /></button></div>}
    {qualityOpen && <div className="drawer-backdrop" onClick={() => setQualityOpen(false)}><aside className="quality-drawer" aria-label="Data health" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}><div className="drawer-heading"><div><div className="eyebrow">SOURCE TRANSPARENCY</div><h2>Data you can trace.</h2></div><button aria-label="Close data health" onClick={() => setQualityOpen(false)}><X size={20} /></button></div><p className="drawer-intro">Publication time tells you how old a forecast is. Last checked tells you when we successfully asked Elexon for updates.</p>
      {quality.data?.datasets.map(d => <div className="source-status" key={d.dataset}><h3><Database size={17} />{d.dataset}<span className={`pill ${d.stale || d.error ? 'warning' : ''}`}>{d.error ? 'Source issue' : d.stale ? 'Check overdue' : 'Up to date'}</span></h3><dl><dt>Stored records</dt><dd>{number(d.records)}</dd><dt>Last successful check</dt><dd>{dateTime(d.last_checked)}</dd><dt>Check age</dt><dd>{age(d.last_checked)}</dd><dt>Latest source publication</dt><dd>{dateTime(d.latest_publication)}</dd><dt>Latest target</dt><dd>{dateTime(d.latest_target)}</dd><dt>First stored target</dt><dd>{dateTime(d.first_target)}</dd></dl>{d.error && <div className="source-error">{d.error}</div>}</div>)}
      <div className="source-status"><h3><RefreshCw size={17} />Synchronisation</h3><p>Source checks every two minutes. This screen refreshes every 30 seconds. Publication-to-screen timing also depends on Elexon.</p><p>{quality.data?.jobs.length || 0} active jobs shown · {quality.data?.failed_jobs || 0} failed jobs</p>{quality.data?.jobs.map(j => <div className="job-row" key={j.id}><span>#{j.id} {j.kind}</span><span>{j.status}</span></div>)}</div><button className="button primary full-width" onClick={refresh}><RefreshCw size={15} />Check for updates</button><p className="drawer-foot">Refresh requests share a durable job. Existing charts remain available during an upstream outage.</p>
    </aside></div>}
  </div>;
}

function Metric({ label, value, unit, foot, icon, tooltip }: { label: string; value: string; unit: string; foot: string; icon: React.ReactNode; tooltip?: string }) {
  return <div className="card metric"><div className="metric-top"><span title={tooltip}>{label}{tooltip && <Info size={12} />}</span><span className="metric-icon">{icon}</span></div><div className="metric-value">{value}<span>{unit}</span></div><div className="metric-foot">{foot}</div></div>;
}

function Empty({ loading, title, text }: { loading?: boolean; title: string; text: string }) {
  return <div className="empty-state">{loading ? <LoaderCircle className="spin" size={28} /> : <Wind size={32} />}<h3>{loading ? 'Bringing the data into focus…' : title}</h3><p>{loading ? 'Selecting eligible source records and calculating your view.' : text}</p></div>;
}

function Methodology({ availability, setAvailability, openQuality }: { availability: string; setAvailability: (v: string) => void; openQuality: () => void }) {
  return <div className="methodology"><section className="card method-intro"><div className="method-intro-icon"><BookOpen size={30} /></div><div><div className="eyebrow">THE SIMPLE VERSION</div><h2>What was expected. What happened.<br />How far apart were they?</h2><p>We keep checking Elexon for new wind forecasts, remember each published version, and compare decision-time forecasts with actual wind generation. The app provides national wind intelligence; your own demand and contracts stay in your existing systems.</p></div></section>
    <div className="method-steps">{[
      ['01', 'Collect', 'Two Elexon datasets: WINDFOR forecasts and FUELHH actuals, filtered to wind. A background worker keeps checking even when this page is closed.'],
      ['02', 'Select', 'For each delivery target, select the latest eligible forecast before the chosen decision cutoff. Never substitute a later, more accurate forecast.'],
      ['03', 'Compare', 'Match the original target timestamps. Hourly forecast targets are compared with the actual half-hour beginning at that same time. No additional forecasts are invented.'],
      ['04', 'Explain', 'Calculate errors, revisions, coverage, and plain-language findings. Keep decision-time evidence separate from hindsight.'],
    ].map(([n, title, text]) => <section className="card method-step" key={n}><span>{n}</span><h3>{title}</h3><p>{text}</p></section>)}</div>
    <section className="card"><div className="card-heading"><div><h2>Reading the results</h2><p>MW measures the level of power output. All error values use the same unit.</p></div><span className="small-tag">Error = forecast − actual</span></div><div className="example"><div><span>Forecast</span><strong>1,000 <small>MW</small></strong></div><span>−</span><div><span>Actual</span><strong>850 <small>MW</small></strong></div><span>=</span><div><span>Forecast error</span><strong>+150 <small>MW</small></strong></div><p>Actual wind was 150 MW below forecast. This does not mean the client needed to buy 150 MW.</p></div>
    <div className="table-scroll"><table className="definitions"><thead><tr><th>Measure</th><th>How it is calculated</th><th>How to read it</th></tr></thead><tbody><tr><td>Average miss · MAE</td><td>Average of absolute errors</td><td>Typical size of the forecast miss</td></tr><tr><td>Forecast tendency · bias</td><td>Average signed error</td><td>Positive means wind was over-forecast</td></tr><tr><td>Large-error measure · RMSE</td><td>Square root of average squared errors</td><td>Large misses have more influence</td></tr><tr><td>Relative error · WAPE</td><td>Sum of absolute errors ÷ sum of absolute actuals</td><td>Unavailable if actual generation sums to zero</td></tr><tr><td>Coverage</td><td>Matched targets ÷ expected targets</td><td>Missing evidence is not perfect forecasting</td></tr></tbody></table></div></section>
    <div className="two-column"><section className="card method-detail"><ShieldCheck size={22} /><h2>Two ways to reconstruct availability</h2><p>Source publication replay reconstructs what Elexon had published. Receipt replay additionally requires this application to have received the record before the cutoff. Historical imports cannot prove original application receipt.</p><label>Availability rule<select aria-label="Availability rule" value={availability} onChange={e => setAvailability(e.target.value)}><option value="published">Source publication replay</option><option value="received">Application receipt replay</option></select></label></section><section className="card method-detail"><Clock3 size={22} /><h2>Dates, gaps, and honest limitations</h2><p>January decisions run from 1–31 January 2026, with delivery from 2 January–1 February. All display times use Europe/London. Clock-change days are handled in UTC, so repeated hours remain distinct.</p><p>Missing records stay missing. Historical error is not a guaranteed future range. No demand, prices, other fuels, trading, or AI agents are used.</p><button className="text-button" onClick={openQuality}>Inspect data health <ArrowRight size={14} /></button></section></div>
  </div>;
}

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15000, refetchOnWindowFocus: true } } });
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><App /></QueryClientProvider></React.StrictMode>);
