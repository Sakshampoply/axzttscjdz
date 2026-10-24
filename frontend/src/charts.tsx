import { useEffect, useRef } from 'react';
import { init, use, type EChartsCoreOption } from 'echarts/core';
import { LineChart, BarChart, HeatmapChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, VisualMapComponent, AriaComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { Accuracy, Forecast } from './api';

use([LineChart, BarChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, VisualMapComponent, AriaComponent, CanvasRenderer]);
const font = 'DM Sans, sans-serif';
const blue = '#2878ab';
const grid = '#eaf0f4';
const muted = '#8a9aa7';
export const localTime = (value: string | number) => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
export const shortDate = (value: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'Europe/London' }).format(new Date(`${value}T12:00:00Z`));

function Chart({ option, label, height = 330 }: { option: EChartsCoreOption; label: string; height?: number }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current) return;
    const chart = init(element.current, undefined, { renderer: 'canvas' });
    chart.setOption({ animation: false, textStyle: { fontFamily: font }, aria: { enabled: true, description: label }, ...option });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [option, label]);
  return <div ref={element} role="img" aria-label={label} style={{ height, width: '100%' }} />;
}

export function ForecastChart({ data }: { data: Forecast }) {
  const lines = [
    { name: 'Selected forecast', type: 'line', showSymbol: false, connectNulls: false,
      data: data.points.map(p => [Date.parse(p.start_time), p.forecast_mw]),
      lineStyle: { color: blue, width: 3 }, itemStyle: { color: blue },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#2878ab20' }, { offset: 1, color: '#2878ab01' }] } } },
    { name: 'Earlier forecast', type: 'line', showSymbol: false, connectNulls: false,
      data: data.points.map(p => [Date.parse(p.start_time), p.previous_mw]),
      lineStyle: { color: '#a3b8c7', width: 2, type: 'dashed' }, itemStyle: { color: '#a3b8c7' } },
  ];
  if (data.reveal_actuals) lines.push({ name: 'Actual generation', type: 'line', showSymbol: false, connectNulls: false,
    data: data.actual_curve.map(p => [Date.parse(p.start_time), p.generation_mw]),
    lineStyle: { color: '#2b7569', width: 2 }, itemStyle: { color: '#2b7569' } } as typeof lines[0]);
  return <Chart label="Wind generation over the delivery day. An accessible values table is available below." option={{
    grid: { top: 24, bottom: 45, left: 65, right: 22 },
    tooltip: { trigger: 'axis', formatter: (items: { value: [number, number | null]; seriesName: string; marker: string }[]) => {
      if (!items.length) return '';
      const heading = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(new Date(items[0].value[0]));
      return `${heading}<br/>${items.map(i => `${i.marker} ${i.seriesName}: ${i.value[1] === null ? 'Unavailable' : `${i.value[1].toLocaleString()} MW`}`).join('<br/>')}`;
    } },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#dde6ed' } }, axisTick: { show: false },
      axisLabel: { color: muted, formatter: (v: number) => localTime(v), hideOverlap: true }, splitLine: { show: false }, splitNumber: 8 },
    yAxis: { type: 'value', axisLabel: { color: muted, formatter: (v: number) => v.toLocaleString('en-GB') },
      splitLine: { lineStyle: { color: grid, type: 'dashed' } } },
    series: lines,
  }} />;
}

export function RevisionsChart({ data }: { data: Forecast }) {
  return <Chart height={150} label="Changes from the earlier forecast. Negative bars mean expected wind decreased." option={{
    grid: { top: 10, bottom: 30, left: 65, right: 22 }, tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => v === null ? 'Unavailable' : `${Number(v).toLocaleString()} MW` },
    xAxis: { type: 'category', data: data.points.map(p => localTime(p.start_time)), axisTick: { show: false }, axisLine: { lineStyle: { color: '#dde6ed' } }, axisLabel: { color: muted, interval: 3 } },
    yAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: grid } } },
    series: [{ type: 'bar', barMaxWidth: 18, itemStyle: { borderRadius: [3, 3, 0, 0] },
      data: data.points.map(p => ({ value: p.revision_mw, itemStyle: { color: p.revision_mw !== null && p.revision_mw < 0 ? '#d99563' : '#78a9c5' } })) }],
  }} />;
}

export function DailyChart({ data }: { data: Accuracy }) {
  return <Chart height={260} label="Average absolute forecast miss for each delivery day, in MW." option={{
    grid: { top: 20, bottom: 45, left: 60, right: 15 }, tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => v === null ? 'No matched data' : `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })} MW` },
    xAxis: { type: 'category', data: data.daily.map(d => shortDate(d.delivery_date)), axisLabel: { color: muted }, axisTick: { show: false }, axisLine: { lineStyle: { color: grid } } },
    yAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: grid, type: 'dashed' } } },
    series: [{ type: 'bar', barMaxWidth: 20, data: data.daily.map(d => d.mae), itemStyle: { color: '#77a8c5', borderRadius: [4, 4, 0, 0] }, emphasis: { itemStyle: { color: blue } } }],
  }} />;
}

export function HistogramChart({ data }: { data: Accuracy }) {
  return <Chart height={260} label="Distribution of signed forecast errors. Positive errors mean actual wind was below forecast." option={{
    grid: { top: 20, bottom: 48, left: 45, right: 15 }, tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.histogram.map(b => `${Math.round((b.from_mw + b.to_mw) / 2).toLocaleString()}`), axisLabel: { color: muted }, axisTick: { show: false }, axisLine: { lineStyle: { color: grid } }, name: 'Error (MW)', nameLocation: 'middle', nameGap: 32, nameTextStyle: { color: muted } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: muted }, splitLine: { lineStyle: { color: grid, type: 'dashed' } } },
    series: [{ type: 'bar', barCategoryGap: '12%', data: data.histogram.map(b => ({ value: b.count, itemStyle: { color: b.to_mw <= 0 ? '#79aea6' : '#d9a17b', borderRadius: [4, 4, 0, 0] } })) }],
  }} />;
}

export function HeatmapChartView({ data }: { data: Accuracy }) {
  const times = [...new Set(data.points.map(p => p.local_time))];
  const days = data.daily.map(d => d.delivery_date);
  const max = Math.max(...data.points.map(p => Math.abs(p.error_mw ?? 0)), 1);
  return <Chart height={Math.max(240, Math.min(690, days.length * 17 + 110))} label="Forecast error heatmap by delivery date and native target time. Blank cells have no matched evidence." option={{
    grid: { top: 18, bottom: 75, left: 68, right: 16 },
    tooltip: { position: 'top', formatter: (p: { value: [number, number, number] }) => `${shortDate(days[p.value[1]])} · ${times[p.value[0]]}<br/>${Math.round(p.value[2]).toLocaleString()} MW error` },
    xAxis: { type: 'category', data: times, splitArea: { show: true }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: muted, interval: 3, formatter: (v: string) => v.split(' ')[0] } },
    yAxis: { type: 'category', data: days.map(shortDate), inverse: true, splitArea: { show: true }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: muted } },
    visualMap: { min: -max, max, calculable: false, orient: 'horizontal', left: 'center', bottom: 4,
      text: ['Actual below forecast', 'Actual above forecast'], textStyle: { color: '#768a99', fontSize: 10 }, itemWidth: 10, itemHeight: 160,
      inRange: { color: ['#55949b', '#e7efef', '#f8f9f8', '#efd8c4', '#cb8755'] } },
    series: [{ type: 'heatmap', data: data.points.filter(p => p.error_mw !== null).map(p => [times.indexOf(p.local_time), days.indexOf((p as unknown as { delivery_date: string }).delivery_date), p.error_mw]), itemStyle: { borderWidth: 2, borderColor: '#fff', borderRadius: 2 }, emphasis: { itemStyle: { borderColor: '#294e68', borderWidth: 1 } } }],
  }} />;
}
