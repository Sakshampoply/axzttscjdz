export type Theme = "dark" | "light";
export const THEME_KEY = "gridbricks-theme-v1";

export function initialTheme(): Theme {
  const current = document.documentElement.dataset.theme;
  if (current === "light" || current === "dark") return current;
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export const chartPalette = {
  dark: {
    forecast: "#22d3ee",
    comparison: "#a78bfa",
    actual: "#a78bfa",
    text: "#9baec8",
    grid: "#263246",
    axis: "#2a374b",
    tooltip: "#1b283b",
    tooltipBorder: "#35465d",
    tooltipText: "#f1f5f9",
    area: "#22d3ee25",
  },
  light: {
    forecast: "#007f98",
    comparison: "#7354ce",
    actual: "#7354ce",
    text: "#53647a",
    grid: "#dfe6ef",
    axis: "#cbd5e1",
    tooltip: "#ffffff",
    tooltipBorder: "#cbd5e1",
    tooltipText: "#172337",
    area: "#007f981a",
  },
};
