import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bug,
  Code2,
  GitCompare,
  Layers,
  Shield,
  Zap,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const features = [
  {
    icon: Activity,
    title: "Agent traces",
    description:
      "Capture every step of agent execution — planning, retrieval, tool calls, and LLM responses.",
  },
  {
    icon: Bug,
    title: "Debugging",
    description:
      "Inspect failures with full context: inputs, outputs, errors, and parent-child span relationships.",
  },
  {
    icon: BarChart3,
    title: "Evaluations",
    description:
      "Run agents against datasets and score outputs with configurable LLM-as-a-judge evaluators.",
  },
  {
    icon: GitCompare,
    title: "Regression testing",
    description:
      "Compare agent versions side-by-side and catch performance regressions before they ship.",
  },
  {
    icon: Zap,
    title: "Cost & latency",
    description:
      "Track token usage, estimated cost, and latency across models, agents, and environments.",
  },
  {
    icon: Code2,
    title: "Developer SDK",
    description:
      "Instrument any Python agent with a lightweight SDK — no vendor lock-in to a specific framework.",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-border/60">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <Layers className="h-5 w-5" />
            AgentLens
          </div>
          <nav className="flex items-center gap-3">
            <Link
              href="/login"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Sign in
            </Link>
            <Link href="/signup" className={buttonVariants({ size: "sm" })}>
              Start Monitoring
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 py-24">
          <div className="max-w-3xl">
            <p className="mb-4 text-sm font-medium text-muted-foreground">
              AI agent observability platform
            </p>
            <h1 className="text-4xl font-semibold tracking-tight md:text-6xl">
              Understand what your AI agents actually do.
            </h1>
            <p className="mt-6 text-lg text-muted-foreground md:text-xl">
              Observe, evaluate, debug, and improve AI agents in production.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/signup" className={buttonVariants({ size: "lg" })}>
                Start Monitoring
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
              <Link
                href="/login"
                className={buttonVariants({ variant: "outline", size: "lg" })}
              >
                Explore Demo
              </Link>
            </div>
          </div>
        </section>

        <Separator className="opacity-40" />

        <section className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-2xl font-semibold tracking-tight">Built for AI engineering teams</h2>
          <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="rounded-xl border border-border/60 bg-card/50 p-6"
              >
                <feature.icon className="h-5 w-5 text-muted-foreground" />
                <h3 className="mt-4 font-medium">{feature.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{feature.description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-y border-border/60 bg-card/30 py-20">
          <div className="mx-auto max-w-6xl px-4">
            <h2 className="text-2xl font-semibold tracking-tight">Architecture</h2>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              External agents send structured traces through the SDK to a scalable ingestion pipeline.
            </p>
            <pre className="mt-8 overflow-x-auto rounded-xl border border-border/60 bg-background p-6 text-sm leading-relaxed text-muted-foreground">
{`External AI Agent
       ↓
 AgentLens SDK
       ↓
 Ingestion API
       ↓
Trace/Event Pipeline
       ↓
   PostgreSQL
       ↓
Evaluation / Analytics Engine
       ↓
 AgentLens Dashboard`}
            </pre>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-20">
          <div className="flex items-start gap-4 rounded-xl border border-border/60 p-8">
            <Shield className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" />
            <div>
              <h2 className="text-xl font-semibold">Developer-first security</h2>
              <p className="mt-2 text-muted-foreground">
                JWT authentication, hashed credentials, organization isolation, and API key auth for
                SDK ingestion — designed for production AI workloads.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-muted-foreground md:flex-row">
          <p>AgentLens — observability for AI agents</p>
          <div className="flex gap-4">
            <Link href="/login" className="hover:text-foreground">
              Sign in
            </Link>
            <Link href="/signup" className="hover:text-foreground">
              Get started
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
