"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { TraceExplorer } from "@/components/traces/trace-explorer";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { tracesApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatCost, formatDuration, statusClass } from "@/lib/trace-tree";
import { cn } from "@/lib/utils";

function JsonBlock({ value }: { value: unknown }) {
  if (value == null) return <p className="text-sm text-muted-foreground">None</p>;
  return (
    <pre className="max-h-64 overflow-auto rounded-md border border-border/60 bg-background p-3 font-mono text-xs">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

export default function TraceDetailPage() {
  const params = useParams<{ id: string }>();
  const { accessToken } = useAuth();
  const [copied, setCopied] = useState(false);
  const query = useQuery({
    queryKey: ["trace", params.id],
    queryFn: () => tracesApi.get(params.id, accessToken as string),
    enabled: Boolean(params.id && accessToken),
  });

  if (query.isLoading) {
    return <p className="text-muted-foreground">Loading trace...</p>;
  }
  if (query.isError || !query.data) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Trace not found or you do not have access.</AlertDescription>
      </Alert>
    );
  }

  const trace = query.data;

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Link href="/traces" className="text-sm text-muted-foreground hover:text-foreground">
            ← Traces
          </Link>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">{trace.name}</h1>
          <p className="mt-2 font-mono text-sm text-muted-foreground">Trace #{trace.id.slice(0, 8)}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {trace.agent_name ?? "Unnamed agent"}
            {trace.agent_version ? ` · ${trace.agent_version}` : ""}
            {trace.model_version ? ` · ${trace.model_version}` : ""}
            {trace.prompt_version ? ` · prompt ${trace.prompt_version}` : ""}
          </p>
        </div>
        <button
          type="button"
          className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
          onClick={() => {
            void navigator.clipboard.writeText(trace.id);
            setCopied(true);
          }}
        >
          {copied ? "Copied ID" : "Copy trace ID"}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border/60">
          <CardHeader className="pb-2">
            <CardDescription>Status</CardDescription>
            <CardTitle className={statusClass(trace.status)}>{trace.status}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-border/60">
          <CardHeader className="pb-2">
            <CardDescription>Duration</CardDescription>
            <CardTitle>{formatDuration(trace.duration_ms)}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-border/60">
          <CardHeader className="pb-2">
            <CardDescription>Tokens</CardDescription>
            <CardTitle>{trace.total_tokens.toLocaleString()}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {trace.input_tokens.toLocaleString()} in / {trace.output_tokens.toLocaleString()} out
            </p>
          </CardContent>
        </Card>
        <Card className="border-border/60">
          <CardHeader className="pb-2">
            <CardDescription>Cost</CardDescription>
            <CardTitle>{formatCost(trace.total_cost)}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {trace.error_message ? (
        <Alert variant="destructive">
          <AlertDescription>
            {trace.error_type ? `${trace.error_type}: ` : ""}
            {trace.error_message}
          </AlertDescription>
        </Alert>
      ) : null}

      <TraceExplorer trace={trace} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle>Trace input</CardTitle>
          </CardHeader>
          <CardContent>
            <JsonBlock value={trace.input} />
          </CardContent>
        </Card>
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle>Trace output</CardTitle>
          </CardHeader>
          <CardContent>
            <JsonBlock value={trace.output} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
