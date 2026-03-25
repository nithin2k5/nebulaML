import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatMetricValue(v) {
  if (v == null) return "—";
  if (typeof v === "number" && Number.isFinite(v)) {
    if (Number.isInteger(v) && Math.abs(v) < 1e9) return String(v);
    return v.toFixed(3);
  }
  if (typeof v === "object" && !Array.isArray(v)) {
    const parts = Object.entries(v).filter(([, x]) => typeof x === "number" && Number.isFinite(x));
    if (parts.length) return parts.map(([k, x]) => `${k}: ${x.toFixed(3)}`).join(" · ");
    try {
      return JSON.stringify(v);
    } catch {
      return "[object]";
    }
  }
  return String(v);
}
