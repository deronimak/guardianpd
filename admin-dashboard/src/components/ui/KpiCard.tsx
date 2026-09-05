import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { cn } from "../../lib/utils";
import { formatPercent } from "../../lib/format";

export function KpiCard({
  label,
  value,
  delta,
  deltaGoodDirection = "up",
  subtext,
  icon,
}: {
  label: string;
  value: ReactNode;
  delta?: number;
  deltaGoodDirection?: "up" | "down";
  subtext?: string;
  icon?: ReactNode;
}) {
  const isGood = delta === undefined ? null : deltaGoodDirection === "up" ? delta >= 0 : delta <= 0;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs transition-shadow hover:shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-gray-500">{label}</p>
        {icon && <span className="text-gray-300">{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-2.5">
        <p className="text-2xl font-semibold tracking-tight text-gray-900 font-[var(--font-display)]">{value}</p>
        {delta !== undefined && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-medium",
              isGood ? "text-success-600" : "text-danger-600"
            )}
          >
            {delta >= 0 ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}
            {formatPercent(Math.abs(delta))}
          </span>
        )}
      </div>
      {subtext && <p className="mt-1.5 text-xs text-gray-400">{subtext}</p>}
    </div>
  );
}
