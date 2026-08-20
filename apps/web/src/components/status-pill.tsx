import { cn } from "@/lib/utils";

const TONES = {
  pass: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  fail: "border-red-500/30 bg-red-500/10 text-red-400",
  neutral: "border-border/60 bg-muted/40 text-muted-foreground",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-400",
} as const;

export type PillTone = keyof typeof TONES;

export function StatusPill({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: PillTone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function verdictTone(verdict: string): PillTone {
  if (verdict === "pass") return "pass";
  if (verdict === "warn") return "warn";
  if (verdict === "fail") return "fail";
  return "neutral";
}

export function passRateTone(rate: number): PillTone {
  if (rate >= 0.95) return "pass";
  if (rate >= 0.8) return "warn";
  return "fail";
}
