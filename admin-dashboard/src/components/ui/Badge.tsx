import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export type BadgeTone = "gray" | "brand" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<BadgeTone, string> = {
  gray: "bg-gray-100 text-gray-700 ring-gray-200",
  brand: "bg-brand-50 text-brand-700 ring-brand-200",
  success: "bg-success-50 text-success-700 ring-success-100",
  warning: "bg-warning-50 text-warning-700 ring-warning-100",
  danger: "bg-danger-50 text-danger-700 ring-danger-100",
  info: "bg-info-50 text-info-700 ring-info-100",
};

export function Badge({
  tone = "gray",
  dot = true,
  children,
  className,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const dotColor: Record<BadgeTone, string> = {
    gray: "bg-gray-500",
    brand: "bg-brand-500",
    success: "bg-success-500",
    warning: "bg-warning-500",
    danger: "bg-danger-500",
    info: "bg-info-500",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
        toneClasses[tone],
        className
      )}
    >
      {dot && <span className={cn("size-1.5 rounded-full", dotColor[tone])} />}
      {children}
    </span>
  );
}

const CUSTOMER_STATUS_TONE: Record<string, BadgeTone> = {
  active: "success",
  trial: "info",
  past_due: "warning",
  cancelled: "gray",
  paused: "gray",
};

const INVOICE_STATUS_TONE: Record<string, BadgeTone> = {
  paid: "success",
  open: "info",
  past_due: "warning",
  void: "gray",
  draft: "gray",
};

const PAYMENT_STATUS_TONE: Record<string, BadgeTone> = {
  successful: "success",
  failed: "danger",
  pending: "warning",
  refunded: "gray",
};

const SUBSCRIPTION_STATUS_TONE: Record<string, BadgeTone> = {
  active: "success",
  trial: "info",
  suspended: "danger",
};

function labelize(status: string): string {
  return status
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export function StatusBadge({
  status,
  map,
}: {
  status: string;
  map: "customer" | "invoice" | "payment" | "subscription";
}) {
  const tones = {
    customer: CUSTOMER_STATUS_TONE,
    invoice: INVOICE_STATUS_TONE,
    payment: PAYMENT_STATUS_TONE,
    subscription: SUBSCRIPTION_STATUS_TONE,
  }[map];
  return <Badge tone={tones[status] ?? "gray"}>{labelize(status)}</Badge>;
}
