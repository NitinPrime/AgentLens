"use client";

import Link from "next/link";
import { useState } from "react";

import { DatasetPanel } from "@/components/evaluations/dataset-panel";
import { EvaluatorPanel } from "@/components/evaluations/evaluator-panel";
import { RunPanel } from "@/components/evaluations/run-panel";
import { buttonVariants } from "@/components/ui/button";
import { useWorkspace } from "@/lib/workspace-context";

export default function EvaluationsPage() {
  const { projects, isLoading } = useWorkspace();
  const [projectId, setProjectId] = useState("");
  const selectedId = projectId || projects[0]?.id || "";

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Evaluations</h1>
          <p className="mt-2 text-muted-foreground">
            Score agent output against datasets and evaluators, then compare runs to catch
            regressions.
          </p>
        </div>
        <label className="space-y-1 text-sm">
          <span className="text-muted-foreground">Project</span>
          <select
            className="block h-9 min-w-[220px] rounded-md border border-border bg-background px-2"
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
        </label>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading workspace...</p>
      ) : !selectedId ? (
        <div className="rounded-xl border border-dashed border-border/60 p-10 text-center">
          <p className="text-sm text-muted-foreground">
            Create a project first. Evaluations, datasets, and evaluators all live inside a project.
          </p>
          <Link href="/projects" className={buttonVariants({ className: "mt-4" })}>
            Go to projects
          </Link>
        </div>
      ) : (
        <div className="space-y-6">
          <RunPanel projectId={selectedId} />
          <div className="grid gap-6 xl:grid-cols-2">
            <DatasetPanel projectId={selectedId} />
            <EvaluatorPanel projectId={selectedId} />
          </div>
        </div>
      )}
    </div>
  );
}
