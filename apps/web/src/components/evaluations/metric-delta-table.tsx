"use client";

import { StatusPill } from "@/components/status-pill";
import type { MetricDelta } from "@/lib/api";

const LABELS: Record<string, string> = {
  pass_rate: "Pass rate",
  avg_score: "Average score",
  avg_latency_ms: "Average latency",
  p50_latency_ms: "p50 latency",
  p95_latency_ms: "p95 latency",
  total_cost: "Total cost",
  avg_cost: "Average cost",
  success_rate: "Success rate",
  error_rate: "Error rate",
  avg_tokens: "Average tokens",
};

function formatMetric(metric: string, value: number | null): string {
  if (value == null) return "—";
  if (metric.endsWith("_rate") || metric === "pass_rate") return `${(value * 100).toFixed(1)}%`;
  if (metric.includes("latency") || metric.endsWith("_ms")) {
    return value < 1000 ? `${Math.round(value)}ms` : `${(value / 1000).toFixed(2)}s`;
  }
  if (metric.includes("cost")) return `$${value.toFixed(4)}`;
  if (metric.includes("token")) return Math.round(value).toLocaleString();
  return value.toFixed(3);
}

function deltaLabel(metric: MetricDelta): string {
  if (metric.delta == null) return "—";
  const sign = metric.delta > 0 ? "+" : "";
  if (metric.pct_change != null && !metric.metric.endsWith("_rate")) {
    return `${sign}${formatMetric(metric.metric, metric.delta)} (${sign}${(metric.pct_change * 100).toFixed(1)}%)`;
  }
  return `${sign}${formatMetric(metric.metric, metric.delta)}`;
}

/**
 * Renders one row per compared metric. A metric only gets a verdict pill when
 * both sides have data, so a missing baseline reads as "no data" rather than an
 * improvement.
 */
export function MetricDeltaTable({ metrics }: { metrics: MetricDelta[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border/60 text-muted-foreground">
          <tr>
            <th className="py-2 font-medium">Metric</th>
            <th className="py-2 font-medium">Baseline</th>
            <th className="py-2 font-medium">Candidate</th>
            <th className="py-2 font-medium">Change</th>
            <th className="py-2 font-medium">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => {
            const comparable = metric.baseline != null && metric.candidate != null;
            const improved =
              comparable &&
              metric.delta != null &&
              metric.delta !== 0 &&
              metric.higher_is_better === metric.delta > 0;
            return (
              <tr key={metric.metric} className="border-b border-border/40">
                <td className="py-2.5">{LABELS[metric.metric] ?? metric.metric}</td>
                <td className="py-2.5 tabular-nums text-muted-foreground">
                  {formatMetric(metric.metric, metric.baseline)}
                </td>
                <td className="py-2.5 tabular-nums">
                  {formatMetric(metric.metric, metric.candidate)}
                </td>
                <td className="py-2.5 tabular-nums">{deltaLabel(metric)}</td>
                <td className="py-2.5">
                  {!comparable ? (
                    <StatusPill>no data</StatusPill>
                  ) : metric.regression ? (
                    <StatusPill tone="fail">regression</StatusPill>
                  ) : improved ? (
                    <StatusPill tone="pass">improved</StatusPill>
                  ) : (
                    <StatusPill tone="neutral">flat</StatusPill>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
