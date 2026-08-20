"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AnalyticsCharts } from "@/components/analytics/charts";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { analyticsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";
import { formatCost, formatDuration } from "@/lib/trace-tree";
import { cn } from "@/lib/utils";

const RANGES = [
  { id: "24h", label: "24h" },
  { id: "7d", label: "7d" },
  { id: "30d", label: "30d" },
  { id: "90d", label: "90d" },
  { id: "custom", label: "Custom" },
] as const;

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default function DashboardPage() {
  const { accessToken } = useAuth();
  const { currentOrg, currentOrgId, projects, isLoading } = useWorkspace();
  const [range, setRange] = useState<(typeof RANGES)[number]["id"]>("7d");
  const [projectId, setProjectId] = useState<string>("");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const customReady = range !== "custom" || Boolean(customStart && customEnd);

  const query = useQuery({
    queryKey: ["analytics", currentOrgId, range, projectId, customStart, customEnd],
    queryFn: () =>
      analyticsApi.get(currentOrgId as string, accessToken as string, {
        range,
        projectId: projectId || undefined,
        start: range === "custom" && customStart ? new Date(customStart).toISOString() : undefined,
        end: range === "custom" && customEnd ? new Date(customEnd).toISOString() : undefined,
      }),
    enabled: Boolean(currentOrgId && accessToken && customReady),
  });

  const summary = query.data?.summary;
  const stats = useMemo(
    () => [
      { label: "Total runs", value: summary ? summary.total_runs.toLocaleString() : "—" },
      { label: "Success rate", value: summary ? pct(summary.success_rate) : "—" },
      {
        label: "Average latency",
        value: summary ? formatDuration(summary.avg_latency_ms) : "—",
      },
      { label: "Total tokens", value: summary ? summary.total_tokens.toLocaleString() : "—" },
      { label: "Total cost", value: summary ? formatCost(summary.total_cost) : "—" },
      { label: "Error rate", value: summary ? pct(summary.error_rate) : "—" },
    ],
    [summary],
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-2 text-muted-foreground">
            {currentOrg
              ? `Live metrics for ${currentOrg.name}`
              : "Create a workspace to start monitoring agents."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-8 rounded-md border border-border bg-background px-2 text-sm"
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
          >
            <option value="">All projects</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <div className="flex rounded-md border border-border/60 p-0.5">
            {RANGES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setRange(item.id)}
                className={cn(
                  "rounded px-2.5 py-1 text-xs",
                  range === item.id ? "bg-muted text-foreground" : "text-muted-foreground",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {range === "custom" ? (
        <div className="flex flex-wrap gap-3 text-sm">
          <label className="space-y-1">
            <span className="text-muted-foreground">From</span>
            <input
              type="datetime-local"
              className="block h-8 rounded-md border border-border bg-background px-2"
              value={customStart}
              onChange={(event) => setCustomStart(event.target.value)}
            />
          </label>
          <label className="space-y-1">
            <span className="text-muted-foreground">To</span>
            <input
              type="datetime-local"
              className="block h-8 rounded-md border border-border bg-background px-2"
              value={customEnd}
              onChange={(event) => setCustomEnd(event.target.value)}
            />
          </label>
        </div>
      ) : null}

      {query.isError ? (
        <Alert variant="destructive">
          <AlertDescription>Unable to load analytics. Confirm the API is running.</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {stats.map((stat) => (
          <Card key={stat.label} className="border-border/60">
            <CardHeader className="pb-2">
              <CardDescription>{stat.label}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{stat.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading charts...</p>
      ) : query.data && query.data.summary.total_runs === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 p-10 text-center">
          <p className="text-sm text-muted-foreground">
            No traces in this window. Create a project, generate an API key, and send a run with the SDK.
          </p>
          <Link href="/projects" className={cn(buttonVariants({ className: "mt-4" }))}>
            Go to projects
          </Link>
        </div>
      ) : query.data ? (
        <AnalyticsCharts data={query.data} />
      ) : null}

      <Card className="border-border/60">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Projects</CardTitle>
            <CardDescription>Each project has its own traces, keys, and evaluations.</CardDescription>
          </div>
          <Link href="/projects" className={buttonVariants({ variant: "outline", size: "sm" })}>
            View all
          </Link>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading projects...</p>
          ) : projects.length === 0 ? (
            <p className="text-sm text-muted-foreground">No projects yet.</p>
          ) : (
            <ul className="divide-y divide-border/60">
              {projects.slice(0, 5).map((project) => (
                <li key={project.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="font-medium">{project.name}</p>
                    <p className="text-xs text-muted-foreground">{project.slug}</p>
                  </div>
                  <Link
                    href={`/projects/${project.id}`}
                    className="text-sm text-muted-foreground hover:text-foreground"
                  >
                    Settings
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
