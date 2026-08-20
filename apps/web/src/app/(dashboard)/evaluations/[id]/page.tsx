"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { MetricDeltaTable } from "@/components/evaluations/metric-delta-table";
import { StatusPill, passRateTone, verdictTone } from "@/components/status-pill";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { evaluationsApi, type EvaluationResult } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatCost, formatDuration } from "@/lib/trace-tree";
import { cn } from "@/lib/utils";

function preview(value: unknown): string {
  if (value == null) return "—";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 400 ? `${text.slice(0, 400)}...` : text;
}

function ResultRow({ result }: { result: EvaluationResult }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="border-b border-border/40">
        <td className="py-2.5">
          <button type="button" className="text-left hover:underline" onClick={() => setOpen(!open)}>
            {result.subject_key.slice(0, 8)}
          </button>
          {result.trace_id ? (
            <Link
              href={`/traces/${result.trace_id}`}
              className="ml-2 text-xs text-muted-foreground hover:text-foreground"
            >
              trace
            </Link>
          ) : null}
        </td>
        <td className="py-2.5">{result.evaluator_name}</td>
        <td className="py-2.5">
          <StatusPill tone={result.passed ? "pass" : "fail"}>
            {result.passed ? "pass" : "fail"}
          </StatusPill>
        </td>
        <td className="py-2.5 tabular-nums">{result.score.toFixed(2)}</td>
        <td className="py-2.5 text-muted-foreground">{result.label ?? "—"}</td>
        <td className="max-w-[380px] py-2.5 text-muted-foreground">
          <span className="line-clamp-2">{result.reasoning ?? "—"}</span>
        </td>
      </tr>
      {open ? (
        <tr className="border-b border-border/40 bg-muted/20">
          <td colSpan={6} className="px-2 py-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Output</p>
                <pre className="max-h-48 overflow-auto rounded-md border border-border/60 bg-background p-2 font-mono text-xs">
                  {preview(result.output)}
                </pre>
              </div>
              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Expected
                </p>
                <pre className="max-h-48 overflow-auto rounded-md border border-border/60 bg-background p-2 font-mono text-xs">
                  {preview(result.expected_output)}
                </pre>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

export default function EvaluationRunPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const { accessToken } = useAuth();
  const [onlyFailures, setOnlyFailures] = useState(false);
  const [baselineId, setBaselineId] = useState("");

  const runQuery = useQuery({
    queryKey: ["evaluation-run", runId],
    queryFn: () => evaluationsApi.getRun(runId, accessToken as string),
    enabled: Boolean(runId && accessToken),
  });

  const run = runQuery.data;

  const runsQuery = useQuery({
    queryKey: ["evaluation-runs", run?.project_id],
    queryFn: () => evaluationsApi.listRuns(run?.project_id as string, accessToken as string),
    enabled: Boolean(run?.project_id && accessToken),
  });

  const comparisonQuery = useQuery({
    queryKey: ["evaluation-comparison", runId, baselineId],
    queryFn: () => evaluationsApi.compareRuns(runId, baselineId, accessToken as string),
    enabled: Boolean(runId && baselineId && accessToken),
  });

  const baselines = useMemo(
    () => (runsQuery.data?.items ?? []).filter((item) => item.id !== runId),
    [runsQuery.data, runId],
  );

  const results = useMemo(() => {
    const rows = run?.results ?? [];
    return onlyFailures ? rows.filter((row) => !row.passed) : rows;
  }, [run?.results, onlyFailures]);

  if (runQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading run...</p>;
  }

  if (runQuery.isError || !run) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Unable to load this evaluation run.{" "}
          <Link href="/evaluations" className="underline">
            Back to evaluations
          </Link>
        </AlertDescription>
      </Alert>
    );
  }

  const stats = [
    { label: "Items", value: run.total_items.toLocaleString() },
    { label: "Passed", value: run.passed_count.toLocaleString() },
    { label: "Failed", value: run.failed_count.toLocaleString() },
    { label: "Pass rate", value: `${(run.pass_rate * 100).toFixed(1)}%` },
    { label: "Avg score", value: run.avg_score == null ? "—" : run.avg_score.toFixed(3) },
    { label: "Cost", value: formatCost(run.total_cost) },
  ];

  return (
    <div className="space-y-8">
      <div>
        <Link href="/evaluations" className="text-sm text-muted-foreground hover:text-foreground">
          ← Evaluations
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">{run.name}</h1>
          <StatusPill tone={run.status === "completed" ? passRateTone(run.pass_rate) : "fail"}>
            {run.status}
          </StatusPill>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {run.target === "dataset" ? `Dataset ${run.dataset_name ?? "—"}` : "Recent traces"}
          {run.agent_version ? ` · agent ${run.agent_version}` : ""}
          {run.prompt_version ? ` · prompt ${run.prompt_version}` : ""}
          {run.completed_at ? ` · finished ${new Date(run.completed_at).toLocaleString()}` : ""}
        </p>
      </div>

      {run.error_message ? (
        <Alert variant="destructive">
          <AlertDescription>{run.error_message}</AlertDescription>
        </Alert>
      ) : null}

      {run.skipped_evaluators.length ? (
        <Alert>
          <AlertDescription>
            Skipped {run.skipped_evaluators.join(", ")} because these subjects had no expected
            output. Run against a dataset to score them.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3 xl:grid-cols-6">
        {stats.map((stat) => (
          <Card key={stat.label} className="border-border/60">
            <CardHeader className="pb-2">
              <CardDescription>{stat.label}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{stat.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle>Score by evaluator</CardTitle>
            <CardDescription>Every evaluator that produced a score in this run.</CardDescription>
          </CardHeader>
          <CardContent>
            {run.evaluator_scores.length === 0 ? (
              <p className="text-sm text-muted-foreground">No scores recorded.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-border/60 text-muted-foreground">
                    <tr>
                      <th className="py-2 font-medium">Evaluator</th>
                      <th className="py-2 font-medium">Type</th>
                      <th className="py-2 font-medium">Passed</th>
                      <th className="py-2 font-medium">Pass rate</th>
                      <th className="py-2 font-medium">Avg score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.evaluator_scores.map((score) => (
                      <tr key={score.evaluator_name} className="border-b border-border/40">
                        <td className="py-2.5 font-medium">{score.evaluator_name}</td>
                        <td className="py-2.5 text-muted-foreground">{score.evaluator_type}</td>
                        <td className="py-2.5 tabular-nums">
                          {score.passed}/{score.count}
                        </td>
                        <td className="py-2.5">
                          <StatusPill tone={passRateTone(score.pass_rate)}>
                            {(score.pass_rate * 100).toFixed(0)}%
                          </StatusPill>
                        </td>
                        <td className="py-2.5 tabular-nums">{score.avg_score.toFixed(2)}</td>
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
            <CardTitle>Failure categories</CardTitle>
            <CardDescription>Grouped by the label each evaluator returned.</CardDescription>
          </CardHeader>
          <CardContent>
            {run.failure_categories.length === 0 ? (
              <p className="text-sm text-muted-foreground">No failures in this run.</p>
            ) : (
              <ul className="space-y-2">
                {run.failure_categories.map((category) => {
                  const width = run.failed_count
                    ? Math.max(4, (category.count / run.failed_count) * 100)
                    : 0;
                  return (
                    <li key={category.label} className="space-y-1">
                      <div className="flex items-baseline justify-between text-sm">
                        <span className="font-mono text-xs">{category.label}</span>
                        <span className="tabular-nums text-muted-foreground">{category.count}</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-border/60">
                        <span
                          className="block h-1.5 rounded-full bg-red-400"
                          style={{ width: `${width}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Compare against a baseline</CardTitle>
          <CardDescription>
            Regression check: a pass-rate drop over five points fails, individual checks that flipped
            warn.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Baseline run</span>
            <select
              className="block h-9 w-full max-w-md rounded-md border border-border bg-background px-2"
              value={baselineId}
              onChange={(event) => setBaselineId(event.target.value)}
            >
              <option value="">Select a run...</option>
              {baselines.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {(item.pass_rate * 100).toFixed(0)}% ·{" "}
                  {new Date(item.created_at).toLocaleDateString()}
                </option>
              ))}
            </select>
          </label>

          {!baselineId ? (
            <p className="text-sm text-muted-foreground">
              {baselines.length
                ? "Pick an earlier run to diff this one against."
                : "Only one run exists so far. Run another to compare."}
            </p>
          ) : comparisonQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Comparing...</p>
          ) : comparisonQuery.isError ? (
            <Alert variant="destructive">
              <AlertDescription>Unable to compare these runs.</AlertDescription>
            </Alert>
          ) : comparisonQuery.data ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <StatusPill tone={verdictTone(comparisonQuery.data.verdict)}>
                  {comparisonQuery.data.verdict}
                </StatusPill>
                <p className="text-sm">{comparisonQuery.data.summary}</p>
              </div>

              <MetricDeltaTable metrics={comparisonQuery.data.metrics} />

              {comparisonQuery.data.evaluator_deltas.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-border/60 text-muted-foreground">
                      <tr>
                        <th className="py-2 font-medium">Evaluator</th>
                        <th className="py-2 font-medium">Baseline</th>
                        <th className="py-2 font-medium">Candidate</th>
                        <th className="py-2 font-medium">Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparisonQuery.data.evaluator_deltas.map((delta) => (
                        <tr key={delta.evaluator_name} className="border-b border-border/40">
                          <td className="py-2.5">{delta.evaluator_name}</td>
                          <td className="py-2.5 tabular-nums text-muted-foreground">
                            {delta.baseline_pass_rate == null
                              ? "—"
                              : `${(delta.baseline_pass_rate * 100).toFixed(0)}%`}
                          </td>
                          <td className="py-2.5 tabular-nums">
                            {delta.candidate_pass_rate == null
                              ? "—"
                              : `${(delta.candidate_pass_rate * 100).toFixed(0)}%`}
                          </td>
                          <td
                            className={cn(
                              "py-2.5 tabular-nums",
                              delta.regression ? "text-red-400" : "",
                            )}
                          >
                            {delta.pass_rate_delta == null
                              ? "—"
                              : `${delta.pass_rate_delta > 0 ? "+" : ""}${(delta.pass_rate_delta * 100).toFixed(0)} pts`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Newly failing ({comparisonQuery.data.newly_failing.length})
                  </p>
                  {comparisonQuery.data.newly_failing.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nothing regressed.</p>
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {comparisonQuery.data.newly_failing.slice(0, 20).map((change) => (
                        <li
                          key={`${change.subject_key}-${change.evaluator_name}`}
                          className="rounded-md border border-red-500/20 bg-red-500/5 p-2"
                        >
                          <p className="font-medium">
                            {change.subject_name ?? change.subject_key.slice(0, 8)}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {change.evaluator_name}: {change.baseline_score.toFixed(2)} →{" "}
                            {change.candidate_score.toFixed(2)}
                          </p>
                          {change.reasoning ? (
                            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                              {change.reasoning}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Newly passing ({comparisonQuery.data.newly_passing.length})
                  </p>
                  {comparisonQuery.data.newly_passing.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No new passes.</p>
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {comparisonQuery.data.newly_passing.slice(0, 20).map((change) => (
                        <li
                          key={`${change.subject_key}-${change.evaluator_name}`}
                          className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-2"
                        >
                          <p className="font-medium">
                            {change.subject_name ?? change.subject_key.slice(0, 8)}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {change.evaluator_name}: {change.baseline_score.toFixed(2)} →{" "}
                            {change.candidate_score.toFixed(2)}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader className="flex flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle>Results</CardTitle>
            <CardDescription>
              {results.length} of {run.results.length} shown. Click a subject to see output versus
              expected.
            </CardDescription>
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={onlyFailures}
              onChange={(event) => setOnlyFailures(event.target.checked)}
            />
            Failures only
          </label>
        </CardHeader>
        <CardContent>
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {onlyFailures ? "No failures." : "No results recorded."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border/60 text-muted-foreground">
                  <tr>
                    <th className="py-2 font-medium">Subject</th>
                    <th className="py-2 font-medium">Evaluator</th>
                    <th className="py-2 font-medium">Result</th>
                    <th className="py-2 font-medium">Score</th>
                    <th className="py-2 font-medium">Label</th>
                    <th className="py-2 font-medium">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((result) => (
                    <ResultRow key={result.id} result={result} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Average subject latency:{" "}
        {formatDuration(
          run.results.length
            ? run.results.reduce((sum, row) => sum + (row.latency_ms ?? 0), 0) / run.results.length
            : null,
        )}
      </p>
    </div>
  );
}
