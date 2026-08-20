"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
import { evaluationsApi, type Dataset } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

const SAMPLE_JSONL = `{"name": "capital-fr", "input": "What is the capital of France?", "expected_output": "Paris"}
{"name": "capital-jp", "input": "What is the capital of Japan?", "expected_output": "Tokyo"}`;

type ParsedItem = {
  name?: string;
  input?: unknown;
  expected_output?: unknown;
  metadata?: Record<string, unknown>;
};

/**
 * Accept either a JSON array or newline-delimited JSON so a dataset can be
 * pasted straight out of an export without reformatting.
 */
export function parseDatasetText(text: string): ParsedItem[] {
  const trimmed = text.trim();
  if (!trimmed) return [];

  if (trimmed.startsWith("[")) {
    const parsed = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) throw new Error("Expected a JSON array of items.");
    return parsed as ParsedItem[];
  }

  return trimmed
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line) as ParsedItem;
      } catch {
        throw new Error(`Line ${index + 1} is not valid JSON.`);
      }
    });
}

function DatasetItems({ dataset }: { dataset: Dataset }) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [replace, setReplace] = useState(false);

  const itemsQuery = useQuery({
    queryKey: ["dataset-items", dataset.id],
    queryFn: () => evaluationsApi.listDatasetItems(dataset.id, accessToken as string),
    enabled: Boolean(accessToken),
  });

  const upload = useMutation({
    mutationFn: (items: ParsedItem[]) =>
      evaluationsApi.addDatasetItems(dataset.id, items, accessToken as string, replace),
    onSuccess: (items) => {
      toast.success(`${items.length} item${items.length === 1 ? "" : "s"} saved`);
      setText("");
      void queryClient.invalidateQueries({ queryKey: ["dataset-items", dataset.id] });
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const items = itemsQuery.data ?? [];

  return (
    <div className="space-y-4 border-t border-border/60 pt-4">
      <div className="space-y-2">
        <Label htmlFor={`items-${dataset.id}`}>Add items (JSON array or JSONL)</Label>
        <textarea
          id={`items-${dataset.id}`}
          rows={5}
          spellCheck={false}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={SAMPLE_JSONL}
          className="w-full rounded-md border border-border bg-background p-3 font-mono text-xs"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            disabled={!text.trim() || upload.isPending}
            onClick={() => {
              try {
                const parsed = parseDatasetText(text);
                if (!parsed.length) {
                  toast.error("Nothing to upload.");
                  return;
                }
                upload.mutate(parsed);
              } catch (error) {
                toast.error((error as Error).message);
              }
            }}
          >
            {upload.isPending ? "Saving..." : "Save items"}
          </Button>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={replace}
              onChange={(event) => setReplace(event.target.checked)}
            />
            Replace existing items
          </label>
        </div>
      </div>

      {items.length > 0 ? (
        <div className="max-h-64 overflow-auto rounded-md border border-border/60">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-card text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Input</th>
                <th className="px-3 py-2 font-medium">Expected</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-border/40 align-top">
                  <td className="px-3 py-2 font-medium">{item.name ?? "—"}</td>
                  <td className="max-w-[240px] truncate px-3 py-2 font-mono text-muted-foreground">
                    {typeof item.input === "string" ? item.input : JSON.stringify(item.input)}
                  </td>
                  <td className="max-w-[240px] truncate px-3 py-2 font-mono text-muted-foreground">
                    {item.expected_output == null
                      ? "—"
                      : typeof item.expected_output === "string"
                        ? item.expected_output
                        : JSON.stringify(item.expected_output)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {itemsQuery.isLoading ? "Loading items..." : "No items yet."}
        </p>
      )}
    </div>
  );
}

export function DatasetPanel({ projectId }: { projectId: string }) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const datasetsQuery = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => evaluationsApi.listDatasets(projectId, accessToken as string),
    enabled: Boolean(projectId && accessToken),
  });

  const create = useMutation({
    mutationFn: () =>
      evaluationsApi.createDataset(
        projectId,
        { name, description: description || undefined },
        accessToken as string,
      ),
    onSuccess: (dataset) => {
      toast.success(`Dataset "${dataset.name}" created`);
      setName("");
      setDescription("");
      setExpanded(dataset.id);
      void queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (datasetId: string) =>
      evaluationsApi.deleteDataset(datasetId, accessToken as string),
    onSuccess: () => {
      toast.success("Dataset deleted");
      void queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const datasets = datasetsQuery.data ?? [];

  return (
    <Card className="border-border/60">
      <CardHeader>
        <CardTitle>Datasets</CardTitle>
        <CardDescription>
          Fixed inputs with expected outputs. The SDK can pull these by name and push results back.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="dataset-name">Name</Label>
            <Input
              id="dataset-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="support-qa-golden"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dataset-description">Description</Label>
            <Input
              id="dataset-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional"
            />
          </div>
          <Button type="submit" disabled={!name.trim() || create.isPending}>
            {create.isPending ? "Creating..." : "Create"}
          </Button>
        </form>

        {datasets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {datasetsQuery.isLoading ? "Loading datasets..." : "No datasets yet."}
          </p>
        ) : (
          <ul className="space-y-2">
            {datasets.map((dataset) => {
              const open = expanded === dataset.id;
              return (
                <li
                  key={dataset.id}
                  className={cn(
                    "rounded-lg border border-border/60 p-3 transition-colors",
                    open ? "bg-muted/30" : "",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <button
                      type="button"
                      className="min-w-0 text-left"
                      onClick={() => setExpanded(open ? null : dataset.id)}
                    >
                      <p className="flex items-center gap-2 font-medium">
                        {dataset.name}
                        <StatusPill tone="info">{dataset.item_count} items</StatusPill>
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {dataset.description || "No description"}
                      </p>
                    </button>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpanded(open ? null : dataset.id)}
                      >
                        {open ? "Hide" : "Items"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 hover:text-red-300"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Delete "${dataset.name}" and all of its items? Evaluation runs that used it are kept.`,
                            )
                          ) {
                            remove.mutate(dataset.id);
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                  {open ? <DatasetItems dataset={dataset} /> : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
