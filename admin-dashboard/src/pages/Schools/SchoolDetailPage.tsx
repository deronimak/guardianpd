import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Archive,
  ArchiveRestore,
  Mail,
  Phone,
  Globe,
  Calendar,
  Pencil,
  Users,
  QrCode,
  Receipt,
  CalendarClock,
  Minus,
  Plus,
  FileClock,
} from "lucide-react";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge, StatusBadge } from "../../components/ui/Badge";
import { Table, Thead, Tbody, Tr, Th, Td } from "../../components/ui/Table";
import { Modal } from "../../components/ui/Modal";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { EmptyState, ErrorState } from "../../components/ui/EmptyState";
import { SkeletonCard } from "../../components/ui/Skeleton";
import { Input, Label, Select } from "../../components/ui/Input";
import { CheckoutLinkModal } from "../../components/ui/CheckoutLinkModal";
import {
  useSchool,
  useUpdateSchool,
  useArchiveSchool,
  useUnarchiveSchool,
  useDeactivateSubscription,
  useReactivateSubscription,
  useUpdateSubscription,
  useAuditLog,
} from "../../api/schools";
import { useInvoices, useCreateManualInvoice } from "../../api/invoices";
import { useToast } from "../../context/ToastContext";
import { formatDate, formatNaira, formatRelativeTime } from "../../lib/format";
import { ApiError } from "../../lib/api";
import type { SubscriptionStatus } from "../../types";

const SUBSCRIPTION_TONE: Record<SubscriptionStatus, "success" | "info" | "danger"> = {
  active: "success",
  trial: "info",
  suspended: "danger",
};

export function SchoolDetailPage() {
  const { schoolId } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const { data: school, isLoading, isError, refetch } = useSchool(schoolId);
  const { data: invoices } = useInvoices("all", schoolId);
  const { data: auditLog } = useAuditLog(schoolId);

  const updateSchool = useUpdateSchool(schoolId ?? "");
  const archiveSchool = useArchiveSchool(schoolId ?? "");
  const unarchiveSchool = useUnarchiveSchool(schoolId ?? "");
  const deactivate = useDeactivateSubscription(schoolId ?? "");
  const reactivate = useReactivateSubscription(schoolId ?? "");
  const updateSubscription = useUpdateSubscription(schoolId ?? "");
  const createManualInvoice = useCreateManualInvoice(schoolId ?? "");

  const [confirmAction, setConfirmAction] = useState<"deactivate" | "reactivate" | "archive" | "unarchive" | null>(
    null
  );
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", address: "", phone: "", billing_email: "", timezone: "" });

  const [subscriptionForm, setSubscriptionForm] = useState<{
    status: SubscriptionStatus;
    price_per_child_naira: number;
    started_at: string;
  } | null>(null);

  const [invoiceConfirmOpen, setInvoiceConfirmOpen] = useState(false);
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null);

  const nextDueInvoice = useMemo(() => {
    if (!invoices) return null;
    return [...invoices]
      .filter((inv) => inv.status !== "paid")
      .sort((a, b) => (a.due_date < b.due_date ? -1 : 1))[0] ?? null;
  }, [invoices]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (isError || !school) {
    return <ErrorState title="Couldn't load this school" onRetry={() => refetch()} />;
  }

  const openEdit = () => {
    setEditForm({
      name: school.name,
      address: school.address ?? "",
      phone: school.phone ?? "",
      billing_email: school.billing_email ?? "",
      timezone: school.timezone,
    });
    setEditOpen(true);
  };

  const openSubscriptionEditor = () => {
    setSubscriptionForm({
      status: school.subscription_status,
      price_per_child_naira: school.price_per_child_naira,
      started_at: school.started_at.slice(0, 10),
    });
  };

  const handleConfirm = () => {
    if (confirmAction === "deactivate") {
      deactivate.mutate(undefined, {
        onSuccess: () => showToast({ kind: "info", title: "Subscription suspended", description: `${school.name}'s access is now suspended.` }),
      });
    } else if (confirmAction === "reactivate") {
      reactivate.mutate(undefined, {
        onSuccess: () => showToast({ kind: "success", title: "Subscription reactivated", description: `${school.name}'s access is active again.` }),
      });
    } else if (confirmAction === "archive") {
      archiveSchool.mutate(undefined, {
        onSuccess: () => showToast({ kind: "info", title: "School archived", description: `${school.name} was archived.` }),
      });
    } else if (confirmAction === "unarchive") {
      unarchiveSchool.mutate(undefined, {
        onSuccess: () => showToast({ kind: "success", title: "School restored", description: `${school.name} was unarchived.` }),
      });
    }
    setConfirmAction(null);
  };

  const handleCreateInvoice = () => {
    createManualInvoice.mutate(undefined, {
      onSuccess: (invoice) => {
        showToast({
          kind: "success",
          title: "Invoice created",
          description: `${formatNaira(invoice.amount_naira)} invoice generated for ${school.name}.`,
        });
        setInvoiceConfirmOpen(false);
        if (invoice.checkout_url) setCheckoutUrl(invoice.checkout_url);
      },
      onError: (err) => {
        showToast({
          kind: "error",
          title: "Couldn't create invoice",
          description: err instanceof ApiError ? err.message : "Something went wrong.",
        });
        setInvoiceConfirmOpen(false);
      },
    });
  };

  return (
    <div>
      <button
        onClick={() => navigate("/schools")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 hover:text-gray-800"
      >
        <ArrowLeft className="size-4" />
        Back to schools
      </button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-tight text-gray-900">
              {school.name}
            </h1>
            <Badge tone={SUBSCRIPTION_TONE[school.subscription_status]}>
              {school.subscription_status[0].toUpperCase() + school.subscription_status.slice(1)}
            </Badge>
            {school.archived_at && <Badge tone="gray">Archived</Badge>}
          </div>
          <p className="mt-1 text-sm text-gray-500">GPD-{String(school.sequence_no).padStart(6, "0")} · {school.slug}</p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" icon={<Pencil className="size-4" />} onClick={openEdit}>
            Edit
          </Button>
          <Button variant="outline" icon={<Receipt className="size-4" />} onClick={() => setInvoiceConfirmOpen(true)}>
            Create & send invoice
          </Button>
          {school.archived_at ? (
            <Button variant="outline" icon={<ArchiveRestore className="size-4" />} onClick={() => setConfirmAction("unarchive")}>
              Unarchive
            </Button>
          ) : (
            <Button variant="dangerGhost" icon={<Archive className="size-4" />} onClick={() => setConfirmAction("archive")}>
              Archive
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={<Users className="size-4" />} label="Guardians" value={String(school.guardian_count)} />
        <StatCard icon={<QrCode className="size-4" />} label="QR codes printed" value={String(school.qr_printed_count)} />
        <StatCard
          icon={<FileClock className="size-4" />}
          label="Next due invoice"
          value={nextDueInvoice ? formatNaira(nextDueInvoice.amount_naira) : "—"}
          subtext={nextDueInvoice ? `Due ${formatDate(nextDueInvoice.due_date)}` : "Nothing outstanding"}
        />
        <StatCard
          icon={<CalendarClock className="size-4" />}
          label="Next billing / renewal date"
          value={formatDate(school.current_period_end)}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Billing history" description="This school's invoices" />
            {!invoices || invoices.length === 0 ? (
              <EmptyState title="No invoices yet" description="Invoices are generated automatically every 30 days." />
            ) : (
              <Table>
                <Thead>
                  <tr>
                    <Th>Period</Th>
                    <Th>Children</Th>
                    <Th>Amount</Th>
                    <Th>Status</Th>
                    <Th>Due</Th>
                    <Th>Paid</Th>
                  </tr>
                </Thead>
                <Tbody>
                  {invoices.map((inv) => (
                    <Tr key={inv.id}>
                      <Td className="text-gray-700">
                        {formatDate(inv.period_start)} – {formatDate(inv.period_end)}
                      </Td>
                      <Td>{inv.child_count}</Td>
                      <Td className="font-medium text-gray-900">{formatNaira(inv.amount_naira)}</Td>
                      <Td>
                        <Badge
                          tone={inv.status === "paid" ? "success" : inv.status === "overdue" ? "danger" : "warning"}
                        >
                          {inv.status[0].toUpperCase() + inv.status.slice(1)}
                        </Badge>
                      </Td>
                      <Td className="text-gray-500">{formatDate(inv.due_date)}</Td>
                      <Td className="text-gray-500">{formatDate(inv.paid_at)}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="Activity log" description="Guardian and student changes at this school" />
            {!auditLog || auditLog.length === 0 ? (
              <EmptyState title="No activity yet" description="Guardian and student changes will show up here." />
            ) : (
              <div className="max-h-96 divide-y divide-gray-50 overflow-y-auto">
                {auditLog.map((entry) => (
                  <div key={entry.id} className="flex items-start gap-3 px-5 py-3">
                    <span
                      className={
                        entry.action === "deleted"
                          ? "flex size-8 shrink-0 items-center justify-center rounded-full bg-danger-50 text-danger-600"
                          : entry.action === "created"
                            ? "flex size-8 shrink-0 items-center justify-center rounded-full bg-success-50 text-success-600"
                            : "flex size-8 shrink-0 items-center justify-center rounded-full bg-info-50 text-info-600"
                      }
                    >
                      <Users className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-gray-900">{entry.summary}</p>
                      <p className="mt-0.5 text-xs text-gray-500">
                        {entry.actor_label} · {formatRelativeTime(entry.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Manage subscription"
              action={
                subscriptionForm ? null : (
                  <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={openSubscriptionEditor}>
                    Edit
                  </Button>
                )
              }
            />
            <CardBody className="space-y-3.5">
              {subscriptionForm ? (
                <div className="space-y-4">
                  <div>
                    <Label>Status</Label>
                    <Select
                      value={subscriptionForm.status}
                      onChange={(e) =>
                        setSubscriptionForm((p) => (p ? { ...p, status: e.target.value as SubscriptionStatus } : p))
                      }
                    >
                      <option value="active">Active</option>
                      <option value="trial">Trial (no billing)</option>
                      <option value="suspended">Suspended</option>
                    </Select>
                  </div>
                  <div>
                    <Label>Price per child</Label>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="icon"
                        disabled={subscriptionForm.price_per_child_naira <= 0}
                        onClick={() =>
                          setSubscriptionForm((p) =>
                            p ? { ...p, price_per_child_naira: Math.max(0, p.price_per_child_naira - 500) } : p
                          )
                        }
                      >
                        <Minus className="size-3.5" />
                      </Button>
                      <span className="flex-1 text-center text-sm font-medium text-gray-900">
                        {formatNaira(subscriptionForm.price_per_child_naira)}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() =>
                          setSubscriptionForm((p) =>
                            p ? { ...p, price_per_child_naira: p.price_per_child_naira + 500 } : p
                          )
                        }
                      >
                        <Plus className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                  <div>
                    <Label>Billing anchor date</Label>
                    <Input
                      type="date"
                      value={subscriptionForm.started_at}
                      onChange={(e) =>
                        setSubscriptionForm((p) => (p ? { ...p, started_at: e.target.value } : p))
                      }
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setSubscriptionForm(null)}>
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      loading={updateSubscription.isPending}
                      onClick={() =>
                        updateSubscription.mutate(
                          {
                            status: subscriptionForm.status,
                            price_per_child_naira: subscriptionForm.price_per_child_naira,
                            started_at: new Date(subscriptionForm.started_at).toISOString(),
                          },
                          {
                            onSuccess: () => {
                              showToast({ kind: "success", title: "Subscription updated", description: "Changes were saved." });
                              setSubscriptionForm(null);
                            },
                            onError: (err) =>
                              showToast({
                                kind: "error",
                                title: "Update failed",
                                description: err instanceof ApiError ? err.message : "Something went wrong.",
                              }),
                          }
                        )
                      }
                    >
                      Save
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <DetailRow label="Status" value={<StatusBadge status={school.subscription_status} map="subscription" />} />
                  <DetailRow label="Price per child" value={formatNaira(school.price_per_child_naira)} />
                  <DetailRow label="Billing anchor" value={formatDate(school.started_at)} />
                  <div className="flex justify-end gap-2 pt-1">
                    {school.subscription_status !== "suspended" ? (
                      <Button size="sm" variant="outline" onClick={() => setConfirmAction("deactivate")}>
                        Suspend
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setConfirmAction("reactivate")}>
                        Reactivate
                      </Button>
                    )}
                  </div>
                </>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Billing period" />
            <CardBody className="space-y-3.5">
              <DetailRow label="Children billed" value={String(school.child_count)} />
              <DetailRow label="Current period" value={`${formatDate(school.current_period_start)} – ${formatDate(school.current_period_end)}`} />
              <DetailRow label="Amount this period" value={formatNaira(school.child_count * school.price_per_child_naira)} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Profile" />
            <CardBody className="space-y-3.5">
              {school.address && (
                <div className="flex items-start gap-2.5 text-sm text-gray-600">
                  <Globe className="mt-0.5 size-4 shrink-0 text-gray-400" />
                  {school.address}
                </div>
              )}
              {school.phone && (
                <div className="flex items-center gap-2.5 text-sm text-gray-600">
                  <Phone className="size-4 text-gray-400" />
                  {school.phone}
                </div>
              )}
              {school.billing_email && (
                <div className="flex items-center gap-2.5 text-sm text-gray-600">
                  <Mail className="size-4 text-gray-400" />
                  {school.billing_email}
                </div>
              )}
              <div className="flex items-center gap-2.5 text-sm text-gray-600">
                <Calendar className="size-4 text-gray-400" />
                Timezone: {school.timezone}
              </div>
            </CardBody>
          </Card>
        </div>
      </div>

      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="Edit school"
        footer={
          <>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={updateSchool.isPending}
              onClick={() =>
                updateSchool.mutate(editForm, {
                  onSuccess: () => {
                    showToast({ kind: "success", title: "School updated", description: "Changes were saved." });
                    setEditOpen(false);
                  },
                  onError: (err) =>
                    showToast({
                      kind: "error",
                      title: "Update failed",
                      description: err instanceof ApiError ? err.message : "Something went wrong.",
                    }),
                })
              }
            >
              Save changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <Label>Name</Label>
            <Input value={editForm.name} onChange={(e) => setEditForm((p) => ({ ...p, name: e.target.value }))} />
          </div>
          <div>
            <Label>Address</Label>
            <Input value={editForm.address} onChange={(e) => setEditForm((p) => ({ ...p, address: e.target.value }))} />
          </div>
          <div>
            <Label>Phone</Label>
            <Input value={editForm.phone} onChange={(e) => setEditForm((p) => ({ ...p, phone: e.target.value }))} />
          </div>
          <div>
            <Label>Billing email</Label>
            <Input
              type="email"
              value={editForm.billing_email}
              onChange={(e) => setEditForm((p) => ({ ...p, billing_email: e.target.value }))}
            />
          </div>
          <div>
            <Label>Timezone</Label>
            <Input value={editForm.timezone} onChange={(e) => setEditForm((p) => ({ ...p, timezone: e.target.value }))} />
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmAction !== null}
        onClose={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
        title={
          confirmAction === "deactivate"
            ? "Suspend this subscription?"
            : confirmAction === "reactivate"
              ? "Reactivate this subscription?"
              : confirmAction === "archive"
                ? "Archive this school?"
                : "Restore this school?"
        }
        description={
          confirmAction === "deactivate"
            ? "This immediately blocks QR code scanning and issuance for this school."
            : confirmAction === "reactivate"
              ? "This restores QR code scanning and issuance for this school."
              : confirmAction === "archive"
                ? "The school is hidden from the default list but its data is kept."
                : "The school becomes visible in the default list again."
        }
        confirmLabel={
          confirmAction === "deactivate"
            ? "Suspend"
            : confirmAction === "reactivate"
              ? "Reactivate"
              : confirmAction === "archive"
                ? "Archive"
                : "Restore"
        }
        danger={confirmAction === "deactivate" || confirmAction === "archive"}
      />

      <ConfirmDialog
        open={invoiceConfirmOpen}
        onClose={() => setInvoiceConfirmOpen(false)}
        onConfirm={handleCreateInvoice}
        title="Create and send invoice?"
        description={`This generates an invoice for ${school.child_count} child(ren) at ${formatNaira(
          school.price_per_child_naira
        )} each (${formatNaira(school.child_count * school.price_per_child_naira)} total) and emails it with a payment link if a billing email is on file.`}
        confirmLabel="Create invoice"
        danger={false}
        loading={createManualInvoice.isPending}
      />

      <CheckoutLinkModal url={checkoutUrl} onClose={() => setCheckoutUrl(null)} />
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  );
}

function StatCard({ icon, label, value, subtext }: { icon: React.ReactNode; label: string; value: string; subtext?: string }) {
  return (
    <Card>
      <CardBody>
        <div className="flex items-center gap-2 text-gray-400">
          {icon}
          <span className="text-xs font-medium text-gray-500">{label}</span>
        </div>
        <p className="mt-2 text-xl font-semibold tracking-tight text-gray-900">{value}</p>
        {subtext && <p className="mt-1 text-xs text-gray-400">{subtext}</p>}
      </CardBody>
    </Card>
  );
}
