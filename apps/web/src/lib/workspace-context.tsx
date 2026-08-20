"use client";

import { useQuery } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { workspaceApi, type Organization, type Project } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const ORG_STORAGE_KEY = "agentlens_org_id";

type WorkspaceContextValue = {
  organizations: Organization[];
  currentOrg: Organization | null;
  currentOrgId: string | null;
  setCurrentOrgId: (id: string) => void;
  projects: Project[];
  isLoading: boolean;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function readStoredOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ORG_STORAGE_KEY);
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { accessToken, isAuthenticated } = useAuth();
  const [selectedOrgId, setOrgIdState] = useState<string | null>(readStoredOrgId);

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => workspaceApi.listOrganizations(accessToken as string),
    enabled: Boolean(isAuthenticated && accessToken),
  });

  const organizations = useMemo(() => orgsQuery.data ?? [], [orgsQuery.data]);

  const currentOrgId = useMemo(() => {
    if (!organizations.length) return null;
    if (selectedOrgId && organizations.some((org) => org.id === selectedOrgId)) {
      return selectedOrgId;
    }
    return organizations[0].id;
  }, [organizations, selectedOrgId]);

  const setCurrentOrgId = useCallback((id: string) => {
    setOrgIdState(id);
    localStorage.setItem(ORG_STORAGE_KEY, id);
  }, []);

  const projectsQuery = useQuery({
    queryKey: ["projects", currentOrgId],
    queryFn: () => workspaceApi.listProjects(currentOrgId as string, accessToken as string),
    enabled: Boolean(currentOrgId && accessToken),
  });

  const currentOrg = organizations.find((org) => org.id === currentOrgId) ?? null;

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      organizations,
      currentOrg,
      currentOrgId,
      setCurrentOrgId,
      projects: projectsQuery.data ?? [],
      isLoading: orgsQuery.isLoading || Boolean(currentOrgId && projectsQuery.isLoading),
    }),
    [
      organizations,
      orgsQuery.isLoading,
      currentOrg,
      currentOrgId,
      setCurrentOrgId,
      projectsQuery.data,
      projectsQuery.isLoading,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within WorkspaceProvider");
  }
  return context;
}
