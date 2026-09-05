export type SubscriptionStatus = "active" | "trial" | "suspended";

export type InvoiceStatus = "pending" | "paid" | "overdue" | "cancelled";

export type InvoiceListFilter = "upcoming" | "unpaid" | "overdue" | "all";

export interface InvoiceUpdateRequest {
  child_count?: number;
  amount_naira?: number;
  due_date?: string;
}

// Matches SchoolWithSubscriptionOut (backend/app/schemas/school.py) — the
// list-view shape. School Detail additionally fetches SchoolDetail below.
export interface School {
  id: string;
  sequence_no: number;
  name: string;
  slug: string;
  status: string;
  timezone: string;
  billing_email: string | null;
  phone: string | null;
  created_at: string;
  subscription_status: SubscriptionStatus;
  archived_at: string | null;
}

// Matches SchoolDetailOut — adds live tenant-DB child count and the
// current billing-period window, neither present on the list shape.
export interface SchoolDetail {
  id: string;
  sequence_no: number;
  name: string;
  slug: string;
  address: string | null;
  phone: string | null;
  timezone: string;
  billing_email: string | null;
  subscription_status: SubscriptionStatus;
  price_per_child_naira: number;
  started_at: string;
  current_period_start: string;
  current_period_end: string;
  child_count: number;
  guardian_count: number;
  qr_printed_count: number;
  archived_at: string | null;
}

export interface SubscriptionUpdateRequest {
  status?: SubscriptionStatus;
  price_per_child_naira?: number;
  started_at?: string;
}

// Matches AuditLogEntryOut (backend/app/schemas/audit.py)
export interface AuditLogEntry {
  id: string;
  entity_type: "guardian" | "student";
  entity_id: string;
  action: "created" | "updated" | "deleted" | "linked";
  summary: string;
  actor_label: string;
  created_at: string;
}

export interface SchoolEnrollRequest {
  name: string;
  slug: string;
  address: string;
  phone: string;
  admin_name: string;
  admin_email: string;
  admin_temp_password: string;
  timezone: string;
  billing_email?: string;
}

export interface SchoolUpdateRequest {
  name?: string;
  address?: string;
  phone?: string;
  billing_email?: string;
  timezone?: string;
}

// Matches InvoiceOut (backend/app/schemas/billing.py)
export interface Invoice {
  id: string;
  school_id: string;
  school_name: string;
  period_start: string;
  period_end: string;
  child_count: number;
  amount_naira: number;
  status: InvoiceStatus;
  due_date: string;
  paid_at: string | null;
  created_at: string;
}

// Matches ManualInvoiceOut — POST /platform/schools/{id}/invoices
export interface ManualInvoiceResult extends Invoice {
  checkout_url: string | null;
}
