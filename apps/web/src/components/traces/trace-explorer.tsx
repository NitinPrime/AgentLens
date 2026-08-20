"use client";

import { useEffect, useMemo, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { TraceDetail, TraceSpan } from "@/lib/api";
import { buildSpanTree, formatCost, formatDuration, statusClass } from "@/lib/trace-tree";
import { cn } from "@/lib/utils";

function JsonBlock({ value, empty = "None" }: { value: unknown; empty?: string }) {
  if (value == null || value === "") {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border/60 bg-background p-3 font-mono text-xs leading-relaxed">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}

function waterfallStyle(traceStart: string, totalMs: number, span: TraceSpan) {
  const start = new Date(span.start_time).getTime() - new Date(traceStart).getTime();
  const duration = span.duration_ms ?? 0;
  const left = totalMs > 0 ? Math.max(0, (start / totalMs) * 100) : 0;
  const width = totalMs > 0 ? Math.max(0.8, (duration / totalMs) * 100) : 100;
  return { left: `${left}%`, width: `${Math.min(width, 100 - left)}%` };
}

function SpanDetail({ span }: { span: TraceSpan }) {
  const childrenNote = span.parent_span_id ? `Parent ${span.parent_span_id.slice(0, 8)}` : "Root span";
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-lg font-medium">{span.name}</p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{span.id}</p>
          </div>
          <span className={cn("text-sm", statusClass(span.status))}>{span.status}</span>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {span.type} · {formatDuration(span.duration_ms)} · {childrenNote}
        </p>
      </div>

      {span.error_message ? (
        <Alert variant="destructive">
          <AlertDescription>
            {span.error_type ? `${span.error_type}: ` : ""}
            {span.error_message}
          </AlertDescription>
        </Alert>
      ) : null}

      <Section title="Timing">
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt className="text-muted-foreground">Start</dt>
            <dd>{new Date(span.start_time).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">End</dt>
            <dd>{span.end_time ? new Date(span.end_time).toLocaleString() : "—"}</dd>
          </div>
        </dl>
      </Section>

      {span.llm_call ? (
        <>
          <Section title="LLM">
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Provider</dt>
                <dd>{span.llm_call.provider}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Model</dt>
                <dd>{span.llm_call.model}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Tokens</dt>
                <dd>
                  {span.llm_call.input_tokens.toLocaleString()} in /{" "}
                  {span.llm_call.output_tokens.toLocaleString()} out
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Cost</dt>
                <dd>{formatCost(span.llm_call.estimated_cost)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Latency</dt>
                <dd>{formatDuration(span.llm_call.latency_ms)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Temperature</dt>
                <dd>{span.llm_call.temperature ?? "—"}</dd>
              </div>
            </dl>
          </Section>
          <Section title="Prompt / messages">
            <JsonBlock value={span.llm_call.messages ?? span.input} />
          </Section>
          <Section title="Completion">
            <JsonBlock value={span.llm_call.completion ?? span.output} />
          </Section>
        </>
      ) : null}

      {span.tool_call ? (
        <>
          <Section title="Tool">
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Name</dt>
                <dd>{span.tool_call.name}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Retries</dt>
                <dd>{span.tool_call.retry_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Duration</dt>
                <dd>{formatDuration(span.tool_call.duration_ms)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Status</dt>
                <dd className={statusClass(span.tool_call.status)}>{span.tool_call.status}</dd>
              </div>
            </dl>
          </Section>
          {span.tool_call.error ? (
            <Alert variant="destructive">
              <AlertDescription>{span.tool_call.error}</AlertDescription>
            </Alert>
          ) : null}
          <Section title="Arguments">
            <JsonBlock value={span.tool_call.arguments ?? span.input} />
          </Section>
          <Section title="Output">
            <JsonBlock value={span.tool_call.output ?? span.output} />
          </Section>
        </>
      ) : null}

      {!span.llm_call && !span.tool_call ? (
        <>
          <Section title="Input">
            <JsonBlock value={span.input} />
          </Section>
          <Section title="Output">
            <JsonBlock value={span.output} />
          </Section>
        </>
      ) : null}

      <Section title="Metadata">
        <JsonBlock value={span.metadata} />
      </Section>
    </div>
  );
}

export function TraceExplorer({ trace }: { trace: TraceDetail }) {
  const tree = useMemo(() => buildSpanTree(trace.spans), [trace.spans]);
  const defaultSpan =
    tree.find((row) => row.span.status === "error")?.span.id ?? tree[0]?.span.id ?? null;
  const [selectedId, setSelectedId] = useState<string | null>(defaultSpan);
  const selected = tree.find((row) => row.span.id === selectedId)?.span ?? null;
  const totalMs = trace.duration_ms || Math.max(...trace.spans.map((s) => s.duration_ms ?? 0), 1);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!tree.length) return;
      const index = tree.findIndex((row) => row.span.id === selectedId);
      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        const next = tree[Math.min(index + 1, tree.length - 1)];
        setSelectedId(next.span.id);
      }
      if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        const prev = tree[Math.max(index - 1, 0)];
        setSelectedId(prev.span.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, tree]);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Execution tree</CardTitle>
          <CardDescription>j/k or arrow keys to move. Click a span for details.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1">
          {tree.length === 0 ? (
            <p className="text-sm text-muted-foreground">No spans recorded for this trace.</p>
          ) : (
            tree.map(({ span, depth }) => {
              const active = span.id === selectedId;
              return (
                <button
                  key={span.id}
                  type="button"
                  onClick={() => setSelectedId(span.id)}
                  className={cn(
                    "flex w-full flex-col gap-1 rounded-md px-2 py-2 text-left text-sm transition-colors",
                    active ? "bg-muted" : "hover:bg-muted/50",
                  )}
                  style={{ paddingLeft: 8 + depth * 16 }}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate font-medium">
                      {span.status === "error" ? "✕ " : ""}
                      {span.name}
                      <span className="ml-2 text-xs font-normal text-muted-foreground">{span.type}</span>
                    </span>
                    <span className={cn("shrink-0 tabular-nums", statusClass(span.status))}>
                      {formatDuration(span.duration_ms)}
                    </span>
                  </div>
                  <div className="relative h-1.5 w-full rounded-full bg-border/60">
                    <span
                      className={cn(
                        "absolute top-0 h-1.5 rounded-full",
                        span.status === "error" ? "bg-red-400" : "bg-zinc-400",
                      )}
                      style={waterfallStyle(trace.start_time, totalMs, span)}
                    />
                  </div>
                </button>
              );
            })
          )}
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Span details</CardTitle>
          <CardDescription>Input, output, tokens, cost, and errors.</CardDescription>
        </CardHeader>
        <CardContent>
          {selected ? (
            <SpanDetail span={selected} />
          ) : (
            <p className="text-sm text-muted-foreground">Select a span in the tree.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
