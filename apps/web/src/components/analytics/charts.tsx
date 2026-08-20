"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AnalyticsResponse } from "@/lib/api";
import { formatCost, formatDuration } from "@/lib/trace-tree";

const axis = { fontSize: 11, fill: "#a1a1aa", tickLine: false, axisLine: false };
const grid = { stroke: "#27272a", vertical: false };
const tooltipStyle = {
  backgroundColor: "#18181b",
  border: "1px solid #27272a",
  borderRadius: 8,
  fontSize: 12,
};

function formatTick(iso: string, grain: string) {
  const date = new Date(iso);
  if (grain === "hour") {
    return date.toLocaleTimeString([], { hour: "numeric" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function AnalyticsCharts({ data }: { data: AnalyticsResponse }) {
  const points = data.timeseries.map((point) => ({
    ...point,
    costNum: Number(point.cost),
    successPct: point.runs ? (point.successes / point.runs) * 100 : 0,
    label: formatTick(point.timestamp, data.grain),
  }));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard title="Runs over time">
        <AreaChart data={points}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} />
          <Area type="monotone" dataKey="runs" stroke="#d4d4d8" fill="#3f3f46" fillOpacity={0.5} />
        </AreaChart>
      </ChartCard>
      <ChartCard title="Success rate">
        <LineChart data={points}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} domain={[0, 100]} tickFormatter={(value) => `${value}%`} />
          <Tooltip contentStyle={tooltipStyle} />
          <Line type="monotone" dataKey="successPct" stroke="#4ade80" dot={false} strokeWidth={2} />
        </LineChart>
      </ChartCard>
      <ChartCard title="Latency">
        <LineChart data={points}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} tickFormatter={(value) => formatDuration(value)} />
          <Tooltip contentStyle={tooltipStyle} />
          <Line type="monotone" dataKey="avg_latency_ms" stroke="#93c5fd" dot={false} strokeWidth={2} />
        </LineChart>
      </ChartCard>
      <ChartCard title="Token usage">
        <AreaChart data={points}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} />
          <Tooltip contentStyle={tooltipStyle} />
          <Area type="monotone" dataKey="tokens" stroke="#c4b5fd" fill="#5b21b6" fillOpacity={0.35} />
        </AreaChart>
      </ChartCard>
      <ChartCard title="Cost">
        <AreaChart data={points}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} tickFormatter={(value) => formatCost(value)} />
          <Tooltip contentStyle={tooltipStyle} />
          <Area type="monotone" dataKey="costNum" stroke="#fbbf24" fill="#78350f" fillOpacity={0.35} />
        </AreaChart>
      </ChartCard>
      <ChartCard title="Errors">
        <BarChart data={points}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip contentStyle={tooltipStyle} />
          <Bar dataKey="errors" fill="#f87171" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ChartCard>
      <div className="rounded-xl border border-border/60 bg-card/40 p-4 lg:col-span-2">
        <h3 className="mb-3 text-sm font-medium">Model usage</h3>
        {data.models.length === 0 ? (
          <p className="flex h-56 items-center justify-center text-sm text-muted-foreground">
            No LLM calls in this window.
          </p>
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.models} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid {...grid} />
                <XAxis type="number" {...axis} />
                <YAxis type="category" dataKey="model" width={120} {...axis} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="calls" fill="#a1a1aa" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

function ChartCard({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactElement;
  className?: string;
}) {
  return (
    <div className={`rounded-xl border border-border/60 bg-card/40 p-4 ${className ?? ""}`}>
      <h3 className="mb-3 text-sm font-medium">{title}</h3>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
