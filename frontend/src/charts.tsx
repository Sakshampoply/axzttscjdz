import { useEffect, useMemo, useRef } from "react";
import {
  init,
  use,
  type EChartsCoreOption,
  type EChartsType,
} from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  AriaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EvaluationPoint, ForecastPoint } from "./api";

use([
  LineChart,
  GridComponent,
  TooltipComponent,
  AriaComponent,
  CanvasRenderer,
]);
const cyan = "#22d3ee";
const violet = "#a78bfa";
const number = (n: number) =>
  n.toLocaleString("en-GB", { maximumFractionDigits: 0 });
const londonTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  hour: "2-digit",
  minute: "2-digit",
});
const londonDay = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "short",
});
const londonStamp = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});
interface TooltipItem {
  value: [number, number | null];
  seriesName: string;
  marker: string;
}

export function WindChart({
  points,
  evaluation = false,
}: {
  points: ForecastPoint[] | EvaluationPoint[];
  evaluation?: boolean;
}) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const option = useMemo<EChartsCoreOption>(() => {
    const series = [
      {
        name: "Forecast",
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: points.map((p) => [Date.parse(p.start_time), p.forecast_mw]),
        lineStyle: { color: cyan, width: evaluation ? 2 : 3 },
        itemStyle: { color: cyan },
        areaStyle: evaluation
          ? undefined
          : {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "#22d3ee25" },
                  { offset: 1, color: "#22d3ee00" },
                ],
              },
            },
      },
    ];
    if (evaluation)
      series.push({
        name: "Actual wind",
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: (points as EvaluationPoint[]).map((p) => [
          Date.parse(p.start_time),
          p.actual_mw,
        ]),
        lineStyle: { color: violet, width: 2 },
        itemStyle: { color: violet },
        areaStyle: undefined,
      });
    return {
      useUTC: true,
      animation: false,
      backgroundColor: "transparent",
      textStyle: { fontFamily: "DM Sans, sans-serif" },
      aria: {
        enabled: true,
        description: evaluation
          ? "Earlier day-ahead wind forecasts in cyan and actual generation in violet. All outcomes were available at the selected decision time. Download CSV for the values."
          : "Wind generation forecast in cyan for the next delivery day, using publications available at the selected decision time. Download CSV for the values.",
      },
      grid: { top: 28, bottom: 45, left: 65, right: 24 },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: "#1b283b",
        borderColor: "#35465d",
        textStyle: { color: "#f1f5f9", fontSize: 13 },
        padding: 12,
        formatter: (items: TooltipItem[]) => {
          if (!items.length) return "";
          const lines = items.map(
            (i) =>
              `${i.marker} ${i.seriesName}: <b>${i.value[1] === null ? "Unavailable" : `${number(i.value[1])} MW`}</b>`,
          );
          if (evaluation) {
            const forecast = items.find((i) => i.seriesName === "Forecast")
              ?.value[1];
            const actual = items.find((i) => i.seriesName === "Actual wind")
              ?.value[1];
            if (forecast != null && actual != null) {
              const error = forecast - actual;
              lines.push(
                `Difference: <b>${error > 0 ? "+" : ""}${number(error)} MW</b>`,
              );
            }
          }
          return `<div style="margin-bottom:8px">${londonStamp.format(items[0].value[0])}</div>${lines.join("<br/>")}`;
        },
      },
      xAxis: {
        type: "time",
        min: points.length ? Date.parse(points[0].start_time) : undefined,
        max: points.length
          ? Date.parse(points[points.length - 1].start_time)
          : undefined,
        minInterval: evaluation ? 86400000 : 3600000,
        splitNumber: evaluation ? 6 : 8,
        axisLine: { lineStyle: { color: "#2a374b" } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          color: "#9baec8",
          fontSize: 12,
          hideOverlap: true,
          formatter: (v: number) =>
            (evaluation ? londonDay : londonTime).format(v),
        },
      },
      yAxis: {
        type: "value",
        name: "MW",
        nameTextStyle: { color: "#9baec8", padding: [0, 0, 8, 0] },
        axisLabel: { color: "#9baec8", fontSize: 12, formatter: number },
        splitLine: { lineStyle: { color: "#263246", type: "dashed" } },
      },
      series,
    };
  }, [points, evaluation]);
  useEffect(() => {
    if (!element.current) return;
    const instance = init(element.current, undefined, { renderer: "canvas" });
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);
  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);
  return (
    <div
      className="wind-chart"
      ref={element}
      role="img"
      aria-label={
        evaluation
          ? "Earlier day-ahead wind forecasts and actual wind generation, using only outcomes available at the selected decision time. Missing values appear as gaps."
          : "Wind generation forecast for the next delivery day. All forecasts were published by the selected decision time."
      }
    />
  );
}
