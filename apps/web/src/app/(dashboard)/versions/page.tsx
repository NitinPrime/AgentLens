"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { MetricDeltaTable } from "@/components/evaluations/metric-delta-table";
import { StatusPill, verdictTone } from "@/components/status-pill";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { versionsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";
import { formatCost, formatDuration } from "@/lib/trace-tree";
import { cn } from "@/lib/utils";

const DIMENSIONS = [
  { id: "agent_version", label: "Agent version" },
  { id: "prompt_version", label: "Prompt version" },
  { id: "model_version", label: "Model version" },
  { id: "agent_name", label: "Agent name" },
] as const;

const RANGES = ["24h", "7d", "30d", "90d"] as const;

export default function VersionsPage() {
  const { accessToken } = useAuth();
  const { projects, isLoading } = useWorkspace();
  const [projectId, setProjectId] = useState("");
  const [dimension, setDimension] = useState<string>("agent_version");
  const [range, setRange] = useState<string>("30d");
  const [baselineChoice, setBaseline] = useState("");
  const [candidateChoice, setCandidate] = useState("");

  const selectedId = projectId || projects[0]?.id || "";

  const listQuery = useQuery({
    queryKey: ["versions", selectedId, dimension, range],
    queryFn: () => versionsApi.list(selectedId, accessToken as string, { dimension, range }),
    enabled: Boolean(selectedId && accessToken),
  });

  const versions = useMemo(() => listQuery.data?.versions ?? [], [listQuery.data]);

  // Default to the two most recently seen versions so the page is useful on
  // first load. A stale selection (after switching project, dimension, or
  // range) falls back to the same defaults instead of querying a version that
  // no longer exists in the window.
  const known = versions.map((item) => item.version);
  const candidate = known.includes(candidateChoice) ? candidateChoice : (known[0] ?? "");
  const baseline = known.includes(baselineChoice)
    ? baselineChoice
    : (known.find((version) => version !== candidate) ?? "");

  const compareQuery = useQuery({
    queryKey: ["version-compare", selectedId, dimension, range, baseline, candidate],
    queryFn: () =>
      versionsApi.compare(selectedId, accessToken as string, {
        dimension,
        range,
        baseline,
        candidate,
      }),
    enabled: Boolean(selectedId && accessToken && baseline && candidate && baseline !== candidate),
  });

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Versions</h1>
          <p className="mt-2 text-muted-foreground">
            Roll production traces up by version and diff two of them to catch regressions before
            they spread.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-8 rounded-md border border-border bg-background px-2 text-sm"
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
          <select
            className="h-8 rounded-md border border-border bg-background px-2 text-sm"
            value={dimension}
            onChange={(event) => setDimension(event.target.value)}
          >
            {DIMENSIONS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <div className="flex rounded-md border border-border/60 p-0.5">
            {RANGES.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setRange(item)}
                className={cn(
                  "rounded px-2.5 py-1 text-xs",
                  range === item ? "bg-muted text-foreground" : "text-muted-foreground",
                )}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>

      {listQuery.isError ? (
        <Alert variant="destructive">
          <AlertDescription>Unable to load version stats.</AlertDescription>
        </Alert>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading workspace...</p>
      ) : !selectedId ? (
        <div className="rounded-xl border border-dashed border-border/60 p-10 text-center">
          <p className="text-sm text-muted-foreground">Create a project to track versions.</p>
          <Link href="/projects" className={buttonVariants({ className: "mt-4" })}>
            Go to projects
          </Link>
        </div>
      ) : (
        <>
          <Card className="border-border/60">
            <CardHeader>
              <CardTitle>Version rollup</CardTitle>
              <CardDescription>
                {versions.length
                  ? `${versions.length} distinct value${versions.length === 1 ? "" : "s"} in the last ${range}`
                  : "No traces carried this dimension in the selected window"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {listQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">Loading versions...</p>
              ) : versions.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border/60 p-6 text-sm text-muted-foreground">
                  Send <code className="font-mono text-xs">agent_version</code> or{" "}
                  <code className="font-mono text-xs">prompt_version</code> on your traces to compare
                  releases. The SDK accepts both on{" "}
                  <code className="font-mono text-xs">trace()</code>.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-border/60 text-muted-foreground">
                      <tr>
                        <th className="py-2 font-medium">Version</th>
                        <th className="py-2 font-medium">Runs</th>
                        <th className="py-2 font-medium">Success</th>
                        <th className="py-2 font-medium">p50</th>
                        <th className="py-2 font-medium">p95</th>
                        <th className="py-2 font-medium">Avg tokens</th>
                        <th className="py-2 font-medium">Cost</th>
                        <th className="py-2 font-medium">Last seen</th>
                        <th className="py-2 font-medium">Compare</th>
                      </tr>
                    </thead>
                    <tbody>
                      {versions.map((version) => (
                        <tr key={version.version} className="border-b border-border/40">
                          <td className="py-3 font-medium">{version.version}</td>
                          <td className="py-3 tabular-nums">{version.runs.toLocaleString()}</td>
                          <td className="py-3">
                            <StatusPill
                              tone={
                                version.success_rate >= 0.95
                                  ? "pass"
                                  : version.success_rate >= 0.85
                                    ? "warn"
                                    : "fail"
                              }
                            >
                              {(version.success_rate * 100).toFixed(1)}%
                            </StatusPill>
                          </td>
                          <td className="py-3 tabular-nums">
                            {formatDuration(version.p50_latency_ms)}
                          </td>
                          <td className="py-3 tabular-nums">
                            {formatDuration(version.p95_latency_ms)}
                          </td>
                          <td className="py-3 tabular-nums">
                            {version.avg_tokens == null ? "—" : Math.round(version.avg_tokens)}
                          </td>
                          <td className="py-3 tabular-nums">{formatCost(version.total_cost)}</td>
                          <td className="py-3 text-muted-foreground">
                            {version.last_seen
                              ? new Date(version.last_seen).toLocaleDateString()
                              : "—"}
                          </td>
                          <td className="py-3">
                            <div className="flex gap-1">
                              <button
                                type="button"
                                onClick={() => setBaseline(version.version)}
                                className={cn(
                                  "rounded border border-border/60 px-2 py-0.5 text-xs",
                                  baseline === version.version ? "bg-muted text-foreground" : "",
                                )}
                              >
                                base
                              </button>
                              <button
                                type="button"
                                onClick={() => setCandidate(version.version)}
                                className={cn(
                                  "rounded border border-border/60 px-2 py-0.5 text-xs",
                                  candidate === version.version ? "bg-muted text-foreground" : "",
                                )}
                              >
                                cand
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/60">
            <CardHeader>
              <CardTitle>Regression check</CardTitle>
              <CardDescription>
                Fails on a success-rate drop over five points; warns when latency or cost climbs more
                than 25%.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-3 text-sm">
                <label className="space-y-1">
                  <span className="text-muted-foreground">Baseline</span>
                  <select
                    className="block h-9 min-w-[180px] rounded-md border border-border bg-background px-2"
                    value={baseline}
                    onChange={(event) => setBaseline(event.target.value)}
                  >
                    <option value="">Select...</option>
                    {versions.map((version) => (
                      <option key={version.version} value={version.version}>
                        {version.version}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-muted-foreground">Candidate</span>
                  <select
                    className="block h-9 min-w-[180px] rounded-md border border-border bg-background px-2"
                    value={candidate}
                    onChange={(event) => setCandidate(event.target.value)}
                  >
                    <option value="">Select...</option>
                    {versions.map((version) => (
                      <option key={version.version} value={version.version}>
                        {version.version}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {!baseline || !candidate ? (
                <p className="text-sm text-muted-foreground">
                  Pick a baseline and a candidate to diff.
                </p>
              ) : baseline === candidate ? (
                <p className="text-sm text-muted-foreground">
                  Choose two different versions to compare.
                </p>
              ) : compareQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">Comparing...</p>
              ) : compareQuery.isError ? (
                <Alert variant="destructive">
                  <AlertDescription>
                    Unable to compare. Both versions need traces in this window.
                  </AlertDescription>
                </Alert>
              ) : compareQuery.data ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusPill tone={verdictTone(compareQuery.data.verdict)}>
                      {compareQuery.data.verdict}
                    </StatusPill>
                    <p className="text-sm">{compareQuery.data.summary}</p>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {compareQuery.data.baseline.version} ({compareQuery.data.baseline.runs} runs) vs{" "}
                    {compareQuery.data.candidate.version} ({compareQuery.data.candidate.runs} runs)
                  </p>
                  <MetricDeltaTable metrics={compareQuery.data.metrics} />
                </div>
              ) : null}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
