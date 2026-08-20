"use client";

import { useEffect, useState } from "react";

import { streamUrl, type TraceSummary } from "@/lib/api";

export type LiveState = "idle" | "connecting" | "open" | "error";

const MAX_LIVE_TRACES = 50;

type Snapshot = {
  key: string | null;
  state: LiveState;
  traces: TraceSummary[];
  eventCount: number;
};

function freshSnapshot(key: string | null): Snapshot {
  return { key, state: key ? "connecting" : "idle", traces: [], eventCount: 0 };
}

/**
 * Subscribe to a project's server-sent event feed and keep the most recent
 * traces in state.
 *
 * State is keyed by the connection identity and recomputed during render when
 * that key changes, so switching projects clears the feed without an extra
 * render pass. The browser reconnects an `EventSource` on its own, so the
 * effect only opens the connection and records what arrives. Ingest sends one
 * event per trace update, so the same trace id can arrive repeatedly; entries
 * are merged by id with the newest payload winning.
 */
export function useLiveTraces(projectId: string | null, token: string | null, enabled = true) {
  const key = enabled && projectId && token ? `${projectId}:${token}` : null;
  const [snapshot, setSnapshot] = useState<Snapshot>(() => freshSnapshot(key));
  const current = snapshot.key === key ? snapshot : freshSnapshot(key);

  useEffect(() => {
    if (!key || !projectId || !token) return;

    const update = (change: (previous: Snapshot) => Snapshot) => {
      setSnapshot((previous) => change(previous.key === key ? previous : freshSnapshot(key)));
    };

    const source = new EventSource(streamUrl(projectId, token));

    source.addEventListener("connected", () => {
      update((previous) => ({ ...previous, state: "open" }));
    });

    source.addEventListener("trace", (event) => {
      let trace: TraceSummary;
      try {
        trace = JSON.parse((event as MessageEvent<string>).data) as TraceSummary;
      } catch {
        return; // A malformed frame should not tear down the feed.
      }
      update((previous) => ({
        ...previous,
        state: "open",
        eventCount: previous.eventCount + 1,
        traces: [trace, ...previous.traces.filter((row) => row.id !== trace.id)].slice(
          0,
          MAX_LIVE_TRACES,
        ),
      }));
    });

    for (const name of ["span", "llm_call", "tool_call", "event"]) {
      source.addEventListener(name, () => {
        update((previous) => ({ ...previous, eventCount: previous.eventCount + 1 }));
      });
    }

    source.onerror = () => {
      const closed = source.readyState === EventSource.CLOSED;
      update((previous) => ({ ...previous, state: closed ? "error" : "connecting" }));
    };

    return () => source.close();
  }, [key, projectId, token]);

  return { state: current.state, traces: current.traces, eventCount: current.eventCount };
}
