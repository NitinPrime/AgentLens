"use client";

import { useQuery } from "@tanstack/react-query";

import { StatusPill } from "@/components/status-pill";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { systemApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatCost, formatDuration } from "@/lib/trace-tree";

function uptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

export function PlatformHealth({ orgId }: { orgId: string | null }) {
  const { accessToken } = useAuth();

  const infoQuery = useQuery({
    queryKey: ["system-info"],
    queryFn: () => systemApi.info(accessToken as string),
    enabled: Boolean(accessToken),
  });

  const metricsQuery = useQuery({
    queryKey: ["system-metrics"],
    queryFn: () => systemApi.metrics(accessToken as string),
    enabled: Boolean(accessToken),
    refetchInterval: 15_000,
  });

  const usageQuery = useQuery({
    queryKey: ["usage", orgId],
    queryFn: () => systemApi.usage(orgId as string, accessToken as string),
    enabled: Boolean(orgId && accessToken),
  });

  const info = infoQuery.data;
  const metrics = metricsQuery.data;
  const usage = usageQuery.data;

  const rows: { label: string; value: string }[] = [
    { label: "Version", value: info ? `${info.name} ${info.version}` : "—" },
    { label: "Environment", value: info?.environment ?? "—" },
    { label: "Database", value: info?.database_backend ?? "—" },
    { label: "Token store", value: info?.token_store ?? "—" },
    {
      label: "LLM judge",
      value: info ? (info.judge_configured ? info.judge_model : "heuristic fallback") : "—",
    },
    { label: "Uptime", value: info ? uptime(info.uptime_seconds) : "—" },
    {
      label: "Rate limit",
      value: info
        ? info.rate_limit_enabled
          ? `${info.rate_limit_requests} / ${info.rate_limit_window_seconds}s`
          : "disabled"
        : "—",
    },
    { label: "Requests served", value: metrics ? metrics.requests.toLocaleString() : "—" },
    {
      label: "Error rate",
      value: metrics ? `${(metrics.error_rate * 100).toFixed(2)}%` : "—",
    },
    { label: "API p50", value: metrics ? formatDuration(metrics.p50_ms) : "—" },
    { label: "API p95", value: metrics ? formatDuration(metrics.p95_ms) : "—" },
    {
      label: "Live streams",
      value: metrics
        ? `${metrics.streams.subscribers} subscriber${metrics.streams.subscribers === 1 ? "" : "s"}`
        : "—",
    },
  ];

  const usageRows: { label: string; value: string }[] = usage
    ? [
        { label: "Projects", value: usage.projects.toLocaleString() },
        { label: "Traces", value: usage.traces.toLocaleString() },
        { label: "Spans", value: usage.spans.toLocaleString() },
        { label: "LLM calls", value: usage.llm_calls.toLocaleString() },
        { label: "Tool calls", value: usage.tool_calls.toLocaleString() },
        { label: "Datasets", value: `${usage.datasets} (${usage.dataset_items} items)` },
        { label: "Evaluators", value: usage.evaluators.toLocaleString() },
        { label: "Eval runs", value: usage.evaluation_runs.toLocaleString() },
        { label: "Traces (24h)", value: usage.traces_last_24h.toLocaleString() },
        { label: "Tokens (24h)", value: usage.tokens_last_24h.toLocaleString() },
        { label: "Cost (24h)", value: formatCost(usage.cost_last_24h) },
        {
          label: "Oldest trace",
          value: usage.oldest_trace_at
            ? new Date(usage.oldest_trace_at).toLocaleDateString()
            : "none",
        },
      ]
    : [];

  const slowest = (metrics?.routes ?? [])
    .filter((route) => route.p95_ms != null)
    .sort((a, b) => (b.p95_ms ?? 0) - (a.p95_ms ?? 0))
    .slice(0, 5);

  return (
    <Card className="border-border/60">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Platform health
          {metrics ? (
            <StatusPill tone={metrics.server_errors > 0 ? "warn" : "pass"}>
              {metrics.server_errors > 0 ? `${metrics.server_errors} 5xx` : "healthy"}
            </StatusPill>
          ) : null}
        </CardTitle>
        <CardDescription>
          AgentLens monitors itself with the same in-process metrics registry it exposes at{" "}
          <code className="font-mono text-xs">/api/v1/system/metrics/prometheus</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:grid-cols-4">
          {rows.map((row) => (
            <div key={row.label}>
              <dt className="text-xs text-muted-foreground">{row.label}</dt>
              <dd className="tabular-nums">{row.value}</dd>
            </div>
          ))}
        </dl>

        {usageRows.length ? (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Workspace usage
            </p>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:grid-cols-4">
              {usageRows.map((row) => (
                <div key={row.label}>
                  <dt className="text-xs text-muted-foreground">{row.label}</dt>
                  <dd className="tabular-nums">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}

        {slowest.length ? (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Slowest routes
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border/60 text-muted-foreground">
                  <tr>
                    <th className="py-2 font-medium">Route</th>
                    <th className="py-2 font-medium">Requests</th>
                    <th className="py-2 font-medium">p50</th>
                    <th className="py-2 font-medium">p95</th>
                    <th className="py-2 font-medium">Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {slowest.map((route) => (
                    <tr key={route.route} className="border-b border-border/40">
                      <td className="py-2 font-mono text-xs">{route.route}</td>
                      <td className="py-2 tabular-nums">{route.requests.toLocaleString()}</td>
                      <td className="py-2 tabular-nums">{formatDuration(route.p50_ms)}</td>
                      <td className="py-2 tabular-nums">{formatDuration(route.p95_ms)}</td>
                      <td className="py-2 tabular-nums">
                        {route.client_errors + route.server_errors}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
