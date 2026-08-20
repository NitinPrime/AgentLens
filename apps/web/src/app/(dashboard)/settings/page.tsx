"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { PlatformHealth } from "@/components/system/platform-health";
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
import { ApiClientError, workspaceApi, type Organization } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

function OrganizationSettingsCard({
  org,
  accessToken,
}: {
  org: Organization;
  accessToken: string;
}) {
  const queryClient = useQueryClient();
  const [orgName, setOrgName] = useState(org.name);
  const [orgDescription, setOrgDescription] = useState(org.description ?? "");

  async function saveOrg(event: React.FormEvent) {
    event.preventDefault();
    try {
      await workspaceApi.updateOrganization(
        org.id,
        { name: orgName, description: orgDescription },
        accessToken,
      );
      await queryClient.invalidateQueries({ queryKey: ["organizations"] });
      toast.success("Organization updated");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to update organization.");
    }
  }

  return (
    <Card className="border-border/60">
      <CardHeader>
        <CardTitle>Organization</CardTitle>
        <CardDescription>Owners and admins can rename the current workspace.</CardDescription>
      </CardHeader>
      <form onSubmit={(event) => void saveOrg(event)}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="orgName">Name</Label>
            <Input
              id="orgName"
              value={orgName}
              onChange={(event) => setOrgName(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="orgDescription">Description</Label>
            <Input
              id="orgDescription"
              value={orgDescription}
              onChange={(event) => setOrgDescription(event.target.value)}
            />
          </div>
          <Button type="submit">Save organization</Button>
        </CardContent>
      </form>
    </Card>
  );
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { user, accessToken, updateProfile } = useAuth();
  const { currentOrg, currentOrgId, setCurrentOrgId } = useWorkspace();

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [newOrgName, setNewOrgName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");

  const membersQuery = useQuery({
    queryKey: ["members", currentOrgId],
    queryFn: () => workspaceApi.listMembers(currentOrgId as string, accessToken as string),
    enabled: Boolean(currentOrgId && accessToken),
  });

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    try {
      await updateProfile({ full_name: fullName });
      toast.success("Profile updated");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to update profile.");
    }
  }

  async function createOrg(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    try {
      const org = await workspaceApi.createOrganization({ name: newOrgName }, accessToken);
      await queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setCurrentOrgId(org.id);
      setNewOrgName("");
      toast.success("Organization created");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to create organization.");
    }
  }

  async function invite(event: React.FormEvent) {
    event.preventDefault();
    if (!currentOrgId || !accessToken) return;
    try {
      await workspaceApi.inviteMember(
        currentOrgId,
        { email: inviteEmail, role: "member" },
        accessToken,
      );
      await queryClient.invalidateQueries({ queryKey: ["members", currentOrgId] });
      setInviteEmail("");
      toast.success("Member added");
    } catch (err) {
      toast.error(err instanceof ApiClientError ? err.message : "Unable to invite member.");
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-muted-foreground">Profile, organization, and membership.</p>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Your personal account details.</CardDescription>
        </CardHeader>
        <form onSubmit={(event) => void saveProfile(event)}>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" value={user?.email ?? ""} disabled />
              </div>
              <div className="space-y-2">
                <Label htmlFor="fullName">Full name</Label>
                <Input
                  id="fullName"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                />
              </div>
            </div>
            <Button type="submit">Save profile</Button>
          </CardContent>
        </form>
      </Card>

      {currentOrg && accessToken ? (
        <OrganizationSettingsCard key={currentOrg.id} org={currentOrg} accessToken={accessToken} />
      ) : null}

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>Invite an existing AgentLens user by email.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={(event) => void invite(event)} className="flex flex-col gap-3 sm:flex-row">
            <Input
              type="email"
              required
              placeholder="teammate@company.com"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
            />
            <Button type="submit" className="sm:w-36">
              Invite
            </Button>
          </form>
          {membersQuery.isError ? (
            <Alert variant="destructive">
              <AlertDescription>Unable to load members.</AlertDescription>
            </Alert>
          ) : null}
          <ul className="divide-y divide-border/60">
            {membersQuery.data?.map((member) => (
              <li key={member.id} className="flex items-center justify-between py-3 text-sm">
                <div>
                  <p>{member.full_name || member.email}</p>
                  <p className="text-muted-foreground">{member.email}</p>
                </div>
                <span className="text-muted-foreground">{member.role}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle>New organization</CardTitle>
          <CardDescription>Create another workspace for a team or environment.</CardDescription>
        </CardHeader>
        <form onSubmit={(event) => void createOrg(event)}>
          <CardContent className="flex flex-col gap-3 sm:flex-row">
            <Input
              required
              placeholder="Acme AI"
              value={newOrgName}
              onChange={(event) => setNewOrgName(event.target.value)}
            />
            <Button type="submit" className="sm:w-40">
              Create
            </Button>
          </CardContent>
        </form>
      </Card>

      <PlatformHealth orgId={currentOrgId} />
    </div>
  );
}
