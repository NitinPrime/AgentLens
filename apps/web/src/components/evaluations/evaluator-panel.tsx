"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { StatusPill } from "@/components/status-pill";
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

export function EvaluatorPanel({ projectId }: { projectId: string }) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [typeChoice, setTypeChoice] = useState("");
  // Threshold and config default to the selected type's suggestion; edits are
  // stored against that type so switching types resets the fields without an
  // effect.
  const [edits, setEdits] = useState<{ type: string; threshold: string; config: string } | null>(
    null,
  );

  const typesQuery = useQuery({
    queryKey: ["evaluator-types"],
    queryFn: () => evaluationsApi.listEvaluatorTypes(accessToken as string),
    enabled: Boolean(accessToken),
    staleTime: Infinity,
  });

  const evaluatorsQuery = useQuery({
    queryKey: ["evaluators", projectId],
    queryFn: () => evaluationsApi.listEvaluators(projectId, accessToken as string),
    enabled: Boolean(projectId && accessToken),
  });

  const types = useMemo(() => typesQuery.data ?? [], [typesQuery.data]);
  const type = typeChoice || types[0]?.type || "";
  const selectedType = types.find((item) => item.type === type) ?? null;

  const threshold =
    edits?.type === type ? edits.threshold : selectedType ? String(selectedType.default_threshold) : "";
  const configText =
    edits?.type === type
      ? edits.config
      : selectedType && Object.keys(selectedType.default_config).length
        ? JSON.stringify(selectedType.default_config, null, 2)
        : "";

  const setThreshold = (value: string) => setEdits({ type, threshold: value, config: configText });
  const setConfigText = (value: string) => setEdits({ type, threshold, config: value });

  const create = useMutation({
    mutationFn: () => {
      const config = configText.trim() ? JSON.parse(configText) : undefined;
      return evaluationsApi.createEvaluator(
        projectId,
        {
          name,
          evaluator_type: type,
          threshold: threshold ? Number(threshold) : undefined,
          config,
        },
        accessToken as string,
      );
    },
    onSuccess: (evaluator) => {
      toast.success(`Evaluator "${evaluator.name}" created`);
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["evaluators", projectId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const toggle = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      evaluationsApi.updateEvaluator(id, { is_active: isActive }, accessToken as string),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["evaluators", projectId] }),
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => evaluationsApi.deleteEvaluator(id, accessToken as string),
    onSuccess: () => {
      toast.success("Evaluator deleted");
      void queryClient.invalidateQueries({ queryKey: ["evaluators", projectId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const evaluators = evaluatorsQuery.data ?? [];

  return (
    <Card className="border-border/60">
      <CardHeader>
        <CardTitle>Evaluators</CardTitle>
        <CardDescription>
          Scorers applied to every item in a run. Deterministic checks are free; the LLM judge falls
          back to a heuristic when no API key is configured.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!name.trim() || !type) return;
            try {
              if (configText.trim()) JSON.parse(configText);
            } catch {
              toast.error("Config is not valid JSON.");
              return;
            }
            create.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="evaluator-name">Name</Label>
              <Input
                id="evaluator-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="answer-matches"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="evaluator-type">Type</Label>
              <select
                id="evaluator-type"
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
                value={type}
                onChange={(event) => setTypeChoice(event.target.value)}
              >
                {types.map((item) => (
                  <option key={item.type} value={item.type}>
                    {item.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="evaluator-threshold">Pass threshold</Label>
              <Input
                id="evaluator-threshold"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
              />
            </div>
          </div>

          {selectedType ? (
            <p className="text-xs text-muted-foreground">
              {selectedType.description}
              {selectedType.requires_expected_output
                ? " Requires an expected output on each item."
                : ""}
            </p>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="evaluator-config">Config (JSON)</Label>
            <textarea
              id="evaluator-config"
              rows={3}
              spellCheck={false}
              value={configText}
              onChange={(event) => setConfigText(event.target.value)}
              placeholder="{}"
              className="w-full rounded-md border border-border bg-background p-3 font-mono text-xs"
            />
          </div>

          <Button type="submit" disabled={!name.trim() || create.isPending}>
            {create.isPending ? "Creating..." : "Add evaluator"}
          </Button>
        </form>

        {evaluators.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {evaluatorsQuery.isLoading ? "Loading evaluators..." : "No evaluators yet."}
          </p>
        ) : (
          <ul className="space-y-2">
            {evaluators.map((evaluator) => (
              <li
                key={evaluator.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/60 p-3"
              >
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {evaluator.name}
                    <StatusPill tone={evaluator.is_active ? "pass" : "neutral"}>
                      {evaluator.is_active ? "active" : "paused"}
                    </StatusPill>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {evaluator.evaluator_type} · threshold {evaluator.threshold}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      toggle.mutate({ id: evaluator.id, isActive: !evaluator.is_active })
                    }
                  >
                    {evaluator.is_active ? "Pause" : "Activate"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-400 hover:text-red-300"
                    onClick={() => {
                      if (window.confirm(`Delete evaluator "${evaluator.name}"?`)) {
                        remove.mutate(evaluator.id);
                      }
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
