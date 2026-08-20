"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StatusPill } from "@/components/status-pill";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { tracesApi, type TraceSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useLiveTraces } from "@/lib/use-live-traces";
import { useWorkspace } from "@/lib/workspace-context";
import { formatCost, formatDuration, statusClass } from "@/lib/trace-tree";
import { cn } from "@/lib/utils";

const LIVE_TONES = {
  open: "pass",
  connecting: "warn",
  error: "fail",
  idle: "neutral",
} as const;

export default function TracesPage() {
  const { accessToken } = useAuth();
  const { projects, isLoading } = useWorkspace();
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string>("");
  const [live, setLive] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const selectedId = projectId || projects[0]?.id || "";

  const tracesQuery = useQuery({
    queryKey: ["traces", selectedId],
    queryFn: () => tracesApi.list(selectedId, accessToken as string),
    enabled: Boolean(selectedId && accessToken),
  });

  const stream = useLiveTraces(selectedId || null, accessToken, live);

  const items = useMemo(() => {
    const merged = new Map<string, TraceSummary>();
    for (const trace of tracesQuery.data?.items ?? []) merged.set(trace.id, trace);
    // Streamed rows win: they are newer than whatever the last fetch returned.
    for (const trace of stream.traces) merged.set(trace.id, trace);

    const rows = [...merged.values()].sort(
      (a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime(),
    );
    const needle = search.trim().toLowerCase();
    return rows.filter((trace) => {
      if (statusFilter && trace.status !== statusFilter) return false;
      if (!needle) return true;
      return (
        trace.name.toLowerCase().includes(needle) ||
        (trace.agent_name ?? "").toLowerCase().includes(needle) ||
        trace.id.startsWith(needle)
      );
    });
  }, [tracesQuery.data, stream.traces, statusFilter, search]);

  const liveOnlyCount = useMemo(() => {
    const known = new Set((tracesQuery.data?.items ?? []).map((trace) => trace.id));
    return stream.traces.filter((trace) => !known.has(trace.id)).length;
  }, [tracesQuery.data, stream.traces]);

  const emptyMessage = !projects.length
    ? "Create a project and API key, then send a trace with the SDK."
    : tracesQuery.isLoading
      ? "Loading traces..."
      : statusFilter || search
        ? "No traces match this filter."
        : "No traces yet. Use the Python SDK to send one.";

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Traces</h1>
          <p className="mt-2 text-muted-foreground">
            Live agent executions ingested from the SDK.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Project</span>
            <select
              className="block h-9 min-w-[200px] rounded-md border border-border bg-background px-2"
              value={selectedId}
              onChange={(event) => setProjectId(event.target.value)}
              disabled={!projects.length}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Status</span>
            <select
              className="block h-9 rounded-md border border-border bg-background px-2"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">All</option>
              <option value="success">success</option>
              <option value="error">error</option>
              <option value="running">running</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Search</span>
            <input
              className="block h-9 w-40 rounded-md border border-border bg-background px-2"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="name or agent"
            />
          </label>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Recent runs</CardTitle>
            <CardDescription>
              {tracesQuery.data ? `${tracesQuery.data.total} traces stored` : "Waiting for ingest"}
              {liveOnlyCount ? ` · ${liveOnlyCount} new since load` : ""}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill tone={LIVE_TONES[stream.state]}>
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  stream.state === "open"
                    ? "animate-pulse bg-emerald-400"
                    : stream.state === "connecting"
                      ? "bg-amber-400"
                      : stream.state === "error"
                        ? "bg-red-400"
                        : "bg-muted-foreground",
                )}
              />
              {stream.state === "open"
                ? `live · ${stream.eventCount} events`
                : stream.state === "connecting"
                  ? "connecting"
                  : stream.state === "error"
                    ? "stream lost"
                    : "paused"}
            </StatusPill>
            <Button variant="outline" size="sm" onClick={() => setLive(!live)}>
              {live ? "Pause" : "Go live"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                void queryClient.invalidateQueries({ queryKey: ["traces", selectedId] })
              }
            >
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {tracesQuery.isError ? (
            <Alert variant="destructive">
              <AlertDescription>Unable to load traces.</AlertDescription>
            </Alert>
          ) : isLoading || tracesQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/60 p-8 text-sm text-muted-foreground">
              {emptyMessage}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border/60 text-muted-foreground">
                  <tr>
                    <th className="py-2 font-medium">Name</th>
                    <th className="py-2 font-medium">Agent</th>
                    <th className="py-2 font-medium">Version</th>
                    <th className="py-2 font-medium">Status</th>
                    <th className="py-2 font-medium">Duration</th>
                    <th className="py-2 font-medium">Tokens</th>
                    <th className="py-2 font-medium">Cost</th>
                    <th className="py-2 font-medium">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((trace) => (
                    <tr key={trace.id} className="border-b border-border/40">
                      <td className="py-3">
                        <Link href={`/traces/${trace.id}`} className="font-medium hover:underline">
                          {trace.name}
                        </Link>
                        <p className="font-mono text-xs text-muted-foreground">
                          {trace.id.slice(0, 8)}
                        </p>
                      </td>
                      <td className="py-3 text-muted-foreground">{trace.agent_name ?? "—"}</td>
                      <td className="py-3 text-muted-foreground">{trace.agent_version ?? "—"}</td>
                      <td className={cn("py-3", statusClass(trace.status))}>{trace.status}</td>
                      <td className="py-3">{formatDuration(trace.duration_ms)}</td>
                      <td className="py-3">{trace.total_tokens.toLocaleString()}</td>
                      <td className="py-3">{formatCost(trace.total_cost)}</td>
                      <td className="py-3 text-muted-foreground">
                        {new Date(trace.start_time).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
