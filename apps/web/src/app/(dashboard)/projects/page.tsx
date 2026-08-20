"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiClientError, workspaceApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";
import { cn } from "@/lib/utils";

export default function ProjectsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { accessToken } = useAuth();
  const { currentOrgId, currentOrg, projects, isLoading, setCurrentOrgId } = useWorkspace();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken) {
      setError("You are not signed in.");
      return;
    }
    setError(null);
    setIsCreating(true);
    try {
      let orgId = currentOrgId;
      if (!orgId) {
        const org = await workspaceApi.createOrganization(
          { name: "Personal workspace" },
          accessToken,
        );
        orgId = org.id;
        setCurrentOrgId(org.id);
        await queryClient.invalidateQueries({ queryKey: ["organizations"] });
      }
      const project = await workspaceApi.createProject(
        orgId,
        { name, description: description || undefined },
        accessToken,
      );
      await queryClient.invalidateQueries({ queryKey: ["projects", orgId] });
      toast.success("Project created");
      router.push(`/projects/${project.id}`);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Unable to create project.";
      setError(message);
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Projects</h1>
        <p className="mt-2 text-muted-foreground">
          {currentOrg
            ? `Projects in ${currentOrg.name}`
            : "A workspace will be created automatically with your first project."}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle>All projects</CardTitle>
            <CardDescription>Instrument each agent or service as its own project.</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : projects.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border/60 p-8 text-center">
                <p className="text-sm text-muted-foreground">
                  No projects yet. Create one to generate API keys.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-border/60">
                {projects.map((project) => (
                  <li key={project.id} className="py-4">
                    <Link href={`/projects/${project.id}`} className="block hover:opacity-80">
                      <div className="flex items-baseline justify-between gap-4">
                        <p className="font-medium">{project.name}</p>
                        <p className="font-mono text-xs text-muted-foreground">{project.id.slice(0, 8)}</p>
                      </div>
                      {project.description ? (
                        <p className="mt-1 text-sm text-muted-foreground">{project.description}</p>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader>
            <CardTitle>New project</CardTitle>
            <CardDescription>A project scopes traces, keys, and evaluations.</CardDescription>
          </CardHeader>
          <form onSubmit={(event) => void handleCreate(event)}>
            <CardContent className="space-y-4">
              {error ? (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="projectName">Name</Label>
                <Input
                  id="projectName"
                  required
                  placeholder="Customer Support Agent"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="projectDescription">Description</Label>
                <Input
                  id="projectDescription"
                  placeholder="Production support agent"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </div>
              <button
                type="submit"
                className={cn(buttonVariants(), "w-full")}
                disabled={isCreating}
              >
                {isCreating ? "Creating..." : "Create project"}
              </button>
            </CardContent>
          </form>
        </Card>
      </div>
    </div>
  );
}
