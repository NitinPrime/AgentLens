"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { ApiClientError, workspaceApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

function formatDate(value: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

export default function ProjectSettingsPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const router = useRouter();
  const queryClient = useQueryClient();
  const { accessToken } = useAuth();
  const { currentOrgId } = useWorkspace();

  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [keyName, setKeyName] = useState("Production");
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => {
      const project = await workspaceApi.getProject(projectId, accessToken as string);
      setProjectName(project.name);
      setProjectDescription(project.description ?? "");
      return project;
    },
    enabled: Boolean(projectId && accessToken),
  });

  const keysQuery = useQuery({
    queryKey: ["api-keys", projectId],
    queryFn: () => workspaceApi.listApiKeys(projectId, accessToken as string),
    enabled: Boolean(projectId && accessToken),
  });

  async function saveProject(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    try {
      await workspaceApi.updateProject(
        projectId,
        { name: projectName, description: projectDescription },
        accessToken,
      );
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["projects", currentOrgId] });
      toast.success("Project updated");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to update project.");
    }
  }

  async function createKey(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    try {
      const created = await workspaceApi.createApiKey(projectId, keyName, accessToken);
      setCreatedSecret(created.secret);
      setCopied(false);
      await queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] });
      toast.success("API key created — copy it now");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to create API key.");
    }
  }

  async function revokeKey(keyId: string) {
    if (!accessToken) return;
    try {
      await workspaceApi.revokeApiKey(projectId, keyId, accessToken);
      await queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] });
      toast.success("API key revoked");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to revoke key.");
    }
  }

  async function deleteProject() {
    if (!accessToken) return;
    const confirmed = window.confirm("Delete this project and all of its API keys?");
    if (!confirmed) return;
    try {
      await workspaceApi.deleteProject(projectId, accessToken);
      await queryClient.invalidateQueries({ queryKey: ["projects", currentOrgId] });
      toast.success("Project deleted");
      router.push("/projects");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to delete project.");
    }
  }

  if (projectQuery.isLoading) {
    return <p className="text-muted-foreground">Loading project...</p>;
  }

  if (projectQuery.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Project not found or you do not have access.</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <Link href="/projects" className="text-sm text-muted-foreground hover:text-foreground">
          ← Projects
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          {projectQuery.data?.name ?? "Project"}
        </h1>
        <p className="mt-2 font-mono text-sm text-muted-foreground">{projectId}</p>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Project settings</CardTitle>
          <CardDescription>Name and description are visible to everyone in this organization.</CardDescription>
        </CardHeader>
        <form onSubmit={(event) => void saveProject(event)}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={projectDescription}
                onChange={(event) => setProjectDescription(event.target.value)}
              />
            </div>
            <div className="flex gap-3">
              <Button type="submit">Save</Button>
              <Button type="button" variant="destructive" onClick={() => void deleteProject()}>
                Delete project
              </Button>
            </div>
          </CardContent>
        </form>
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>API keys</CardTitle>
          <CardDescription>
            Use <code className="text-foreground">Authorization: Bearer al_…</code> from the SDK. The
            secret is shown only once.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {createdSecret ? (
            <Alert>
              <AlertDescription className="space-y-3">
                <p className="font-medium">Copy this key now. You will not be able to see it again.</p>
                <code className="block break-all rounded-md border border-border bg-background px-3 py-2 text-sm">
                  {createdSecret}
                </code>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    void navigator.clipboard.writeText(createdSecret);
                    setCopied(true);
                  }}
                >
                  {copied ? "Copied" : "Copy secret"}
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          <form onSubmit={(event) => void createKey(event)} className="flex flex-col gap-3 sm:flex-row">
            <Input
              value={keyName}
              onChange={(event) => setKeyName(event.target.value)}
              placeholder="Key name"
              required
            />
            <Button type="submit" className="sm:w-40">
              Create key
            </Button>
          </form>

          {keysQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading keys...</p>
          ) : keysQuery.data?.length === 0 ? (
            <p className="text-sm text-muted-foreground">No API keys yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border/60 text-muted-foreground">
                  <tr>
                    <th className="py-2 font-medium">Name</th>
                    <th className="py-2 font-medium">Prefix</th>
                    <th className="py-2 font-medium">Created</th>
                    <th className="py-2 font-medium">Last used</th>
                    <th className="py-2 font-medium">Status</th>
                    <th className="py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {keysQuery.data?.map((key) => (
                    <tr key={key.id} className="border-b border-border/40">
                      <td className="py-3">{key.name}</td>
                      <td className="py-3 font-mono text-xs">{key.key_prefix}…</td>
                      <td className="py-3 text-muted-foreground">{formatDate(key.created_at)}</td>
                      <td className="py-3 text-muted-foreground">{formatDate(key.last_used_at)}</td>
                      <td className="py-3">{key.is_revoked ? "Revoked" : "Active"}</td>
                      <td className="py-3 text-right">
                        {key.is_revoked ? null : (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => void revokeKey(key.id)}
                          >
                            Revoke
                          </Button>
                        )}
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
