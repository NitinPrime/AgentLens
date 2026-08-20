import type { TraceSpan } from "@/lib/api";

export type SpanTreeRow = { span: TraceSpan; depth: number };

export function buildSpanTree(spans: TraceSpan[]): SpanTreeRow[] {
  const byParent = new Map<string | null, TraceSpan[]>();
  for (const span of spans) {
    const key = span.parent_span_id;
    const list = byParent.get(key) ?? [];
    list.push(span);
    byParent.set(key, list);
  }
  const rows: SpanTreeRow[] = [];
  const walk = (parentId: string | null, depth: number) => {
    for (const span of byParent.get(parentId) ?? []) {
      rows.push({ span, depth });
      walk(span.id, depth + 1);
    }
  };
  walk(null, 0);
  const seen = new Set(rows.map((row) => row.span.id));
  for (const span of spans) {
    if (!seen.has(span.id)) rows.push({ span, depth: 0 });
  }
  return rows;
}

export function formatDuration(ms: number | null | undefined) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatCost(value: string | number | null | undefined) {
  const amount = typeof value === "number" ? value : Number(value ?? 0);
  if (Number.isNaN(amount)) return "$0.0000";
  return `$${amount.toFixed(4)}`;
}

export function statusClass(status: string) {
  if (status === "error" || status === "failed") return "text-red-400";
  if (status === "running") return "text-amber-400";
  if (status === "success") return "text-emerald-400";
  return "text-muted-foreground";
}
