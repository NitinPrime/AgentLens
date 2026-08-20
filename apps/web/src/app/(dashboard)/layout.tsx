"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { WorkspaceProvider, useWorkspace } from "@/lib/workspace-context";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/traces", label: "Traces" },
  { href: "/evaluations", label: "Evaluations" },
  { href: "/versions", label: "Versions" },
  { href: "/projects", label: "Projects" },
  { href: "/settings", label: "Settings" },
];

function Shell({ children }: { children: React.ReactNode }) {
  const { user, isLoading, isAuthenticated, logout } = useAuth();
  const { organizations, currentOrgId, setCurrentOrgId } = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border/60">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
          <div className="flex min-w-0 items-center gap-6">
            <Link href="/dashboard" className="shrink-0 font-semibold tracking-tight">
              AgentLens
            </Link>
            <nav className="hidden items-center gap-4 text-sm md:flex">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "text-muted-foreground transition-colors hover:text-foreground",
                    pathname === item.href ||
                      (item.href !== "/dashboard" && pathname.startsWith(item.href))
                      ? "text-foreground"
                      : "",
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {organizations.length > 0 ? (
              <select
                className="h-8 max-w-[180px] rounded-md border border-border bg-background px-2 text-sm"
                value={currentOrgId ?? ""}
                onChange={(event) => setCurrentOrgId(event.target.value)}
                aria-label="Current organization"
              >
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            ) : null}
            <span className="hidden truncate text-sm text-muted-foreground sm:inline">
              {user?.full_name || user?.email}
            </span>
            <Button variant="outline" size="sm" onClick={() => void logout()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <WorkspaceProvider>
      <Shell>{children}</Shell>
    </WorkspaceProvider>
  );
}
