"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { StatusPill, passRateTone } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { evaluationsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatCost } from "@/lib/trace-tree";

function defaultRunName() {
  const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
  return `traces ${stamp}`;
}

function runTone(status: string, passRate: number) {
  if (status === "failed") return "fail" as const;
  if (status === "running") return "info" as const;
  return passRateTone(passRate);
}

export function RunPanel({ projectId }: { projectId: string }) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [name, setName] = useState(defaultRunName);
  const [agentName, setAgentName] = useState("");
  const [status, setStatus] = useState("");
  const [agentVersion, setAgentVersion] = useState("");
  const [limit, setLimit] = useState("50");
  const [selected, setSelected] = useState<string[]>([]);

  const evaluatorsQuery = useQuery({
    queryKey: ["evaluators", projectId],
    queryFn: () => evaluationsApi.listEvaluators(projectId, accessToken as string),
    enabled: Boolean(projectId && accessToken),
  });

  const runsQuery = useQuery({
    queryKey: ["evaluation-runs", projectId],
    queryFn: () => evaluationsApi.listRuns(projectId, accessToken as string),
    enabled: Boolean(projectId && accessToken),
  });

  const start = useMutation({
    mutationFn: () =>
      evaluationsApi.createRun(
        projectId,
        {
          name: name.trim() || defaultRunName(),
          target: "traces",
          evaluator_ids: selected.length ? selected : undefined,
          agent_version: agentVersion || undefined,
          selector: {
            agent_name: agentName || undefined,
            status: status || undefined,
            agent_version: agentVersion || undefined,
            limit: Math.max(1, Math.min(2000, Number(limit) || 50)),
          },
        },
        accessToken as string,
      ),
    onSuccess: (run) => {
      toast.success(
        run.status === "completed"
          ? `Scored ${run.total_items} traces · ${(run.pass_rate * 100).toFixed(0)}% pass`
          : `Run ${run.status}`,
      );
      setName(defaultRunName());
      void queryClient.invalidateQueries({ queryKey: ["evaluation-runs", projectId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const evaluators = evaluatorsQuery.data ?? [];
  const activeCount = evaluators.filter((item) => item.is_active).length;
  const runs = runsQuery.data?.items ?? [];

  return (
    <div className="space-y-4">
      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Run on recent traces</CardTitle>
          <CardDescription>
            Scores traces already ingested from this project. Dataset runs need agent outputs, so
            they come from the SDK via <code className="font-mono text-xs">AgentLens.evaluate()</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-1.5 lg:col-span-2">
              <Label htmlFor="run-name">Run name</Label>
              <Input id="run-name" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="run-agent">Agent name</Label>
              <Input
                id="run-agent"
                value={agentName}
                onChange={(event) => setAgentName(event.target.value)}
                placeholder="Any"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="run-status">Trace status</Label>
              <select
                id="run-status"
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option value="">Any</option>
                <option value="success">success</option>
                <option value="error">error</option>
                <option value="running">running</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="run-limit">Max traces</Label>
              <Input
                id="run-limit"
                type="number"
                min={1}
                max={2000}
                value={limit}
                onChange={(event) => setLimit(event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="run-version">Label this run with an agent version</Label>
            <Input
              id="run-version"
              className="sm:max-w-xs"
              value={agentVersion}
              onChange={(event) => setAgentVersion(event.target.value)}
              placeholder="Optional, e.g. v2.1.0"
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Evaluators
            </p>
            {evaluators.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No evaluators yet. Add one below before running.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {evaluators.map((evaluator) => {
                  const checked = selected.includes(evaluator.id);
                  return (
                    <label
                      key={evaluator.id}
                      className="flex items-center gap-2 rounded-full border border-border/60 px-3 py-1 text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, evaluator.id]
                              : current.filter((id) => id !== evaluator.id),
                          )
                        }
                      />
                      {evaluator.name}
                    </label>
                  );
                })}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              {selected.length
                ? `${selected.length} selected`
                : `Nothing selected: all ${activeCount} active evaluator${activeCount === 1 ? "" : "s"} will run.`}
            </p>
          </div>

          <Button
            disabled={start.isPending || (!selected.length && activeCount === 0)}
            onClick={() => start.mutate()}
          >
            {start.isPending ? "Running..." : "Run evaluation"}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Runs</CardTitle>
          <CardDescription>
            {runsQuery.data ? `${runsQuery.data.total} runs recorded` : "No runs yet"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {runsQuery.isLoading ? "Loading runs..." : "No evaluation runs yet."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border/60 text-muted-foreground">
                  <tr>
                    <th className="py-2 font-medium">Run</th>
                    <th className="py-2 font-medium">Target</th>
                    <th className="py-2 font-medium">Items</th>
                    <th className="py-2 font-medium">Pass rate</th>
                    <th className="py-2 font-medium">Avg score</th>
                    <th className="py-2 font-medium">Cost</th>
                    <th className="py-2 font-medium">Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id} className="border-b border-border/40">
                      <td className="py-3">
                        <Link
                          href={`/evaluations/${run.id}`}
                          className="font-medium hover:underline"
                        >
                          {run.name}
                        </Link>
                        <p className="text-xs text-muted-foreground">
                          {run.dataset_name ?? "traces"}
                          {run.agent_version ? ` · ${run.agent_version}` : ""}
                        </p>
                      </td>
                      <td className="py-3 text-muted-foreground">{run.target}</td>
                      <td className="py-3 tabular-nums">{run.total_items}</td>
                      <td className="py-3">
                        <StatusPill tone={runTone(run.status, run.pass_rate)}>
                          {run.status === "completed"
                            ? `${(run.pass_rate * 100).toFixed(0)}%`
                            : run.status}
                        </StatusPill>
                      </td>
                      <td className="py-3 tabular-nums">
                        {run.avg_score == null ? "—" : run.avg_score.toFixed(2)}
                      </td>
                      <td className="py-3 tabular-nums">{formatCost(run.total_cost)}</td>
                      <td className="py-3 text-muted-foreground">
                        {run.completed_at ? new Date(run.completed_at).toLocaleString() : "—"}
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
