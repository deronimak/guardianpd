import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, Link2, MoreHorizontal, Pencil, Ban, Trash2 } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { Card } from "../../components/ui/Card";
import { Table, Thead, Tbody, Tr, Th, Td } from "../../components/ui/Table";
import { Badge } from "../../components/ui/Badge";
import { EmptyState, ErrorState } from "../../components/ui/EmptyState";
import { SkeletonTable } from "../../components/ui/Skeleton";
import { Tabs } from "../../components/ui/Tabs";
import { CheckoutLinkModal } from "../../components/ui/CheckoutLinkModal";
import { Button } from "../../components/ui/Button";
import { Dropdown } from "../../components/ui/Dropdown";
import { Modal } from "../../components/ui/Modal";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Input, Label } from "../../components/ui/Input";
import {
  useInvoices,
  useCreateCheckoutSession,
  useUpdateInvoice,
  useCancelInvoice,
  useDeleteInvoice,
} from "../../api/invoices";
import { useToast } from "../../context/ToastContext";
import { formatDate, formatNaira } from "../../lib/format";
import { downloadCsv } from "../../lib/csv";
import { ApiError } from "../../lib/api";
import type { Invoice, InvoiceListFilter } from "../../types";

const TABS: { key: InvoiceListFilter; label: string }[] = [
  { key: "upcoming", label: "Upcoming" },
  { key: "unpaid", label: "Unpaid" },
  { key: "overdue", label: "Overdue" },
  { key: "all", label: "All" },
];

const STATUS_TONE: Record<string, "success" | "danger" | "warning" | "gray"> = {
  paid: "success",
  overdue: "danger",
  pending: "warning",
  cancelled: "gray",
};

export function InvoicesPage() {
  const [tab, setTab] = useState<InvoiceListFilter>("unpaid");
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null);
  const [editingInvoice, setEditingInvoice] = useState<Invoice | null>(null);
  const [editForm, setEditForm] = useState({ child_count: "", amount_naira: "", due_date: "" });
  const [cancelTarget, setCancelTarget] = useState<Invoice | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Invoice | null>(null);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const { data: invoices, isLoading, isError, refetch } = useInvoices(tab);
  const createCheckoutSession = useCreateCheckoutSession();
  const updateInvoice = useUpdateInvoice();
  const cancelInvoice = useCancelInvoice();
  const deleteInvoice = useDeleteInvoice();

  const exportCsv = () => {
    if (!invoices) return;
    downloadCsv(
      "invoices.csv",
      invoices.map((inv) => ({
        School: inv.school_name,
        "Period start": formatDate(inv.period_start),
        "Period end": formatDate(inv.period_end),
        Children: inv.child_count,
        "Amount (NGN)": inv.amount_naira,
        Status: inv.status,
        Due: formatDate(inv.due_date),
        Paid: formatDate(inv.paid_at),
      }))
    );
    showToast({ kind: "success", title: "Export ready", description: `${invoices.length} invoices exported to CSV.` });
  };

  const getCheckoutLink = (invoiceId: string) => {
    createCheckoutSession.mutate(invoiceId, {
      onSuccess: (result) => setCheckoutUrl(result.checkout_url),
      onError: (err) =>
        showToast({
          kind: "error",
          title: "Couldn't create checkout link",
          description: err instanceof ApiError ? err.message : "Something went wrong.",
        }),
    });
  };

  const openEdit = (invoice: Invoice) => {
    setEditingInvoice(invoice);
    setEditForm({
      child_count: String(invoice.child_count),
      amount_naira: String(invoice.amount_naira),
      due_date: invoice.due_date.slice(0, 10),
    });
  };

  const saveEdit = () => {
    if (!editingInvoice) return;
    const input: { child_count?: number; amount_naira?: number; due_date?: string } = {};
    if (Number(editForm.child_count) !== editingInvoice.child_count) input.child_count = Number(editForm.child_count);
    if (Number(editForm.amount_naira) !== editingInvoice.amount_naira) input.amount_naira = Number(editForm.amount_naira);
    if (editForm.due_date !== editingInvoice.due_date.slice(0, 10)) input.due_date = editForm.due_date;

    updateInvoice.mutate(
      { id: editingInvoice.id, input },
      {
        onSuccess: () => {
          showToast({ kind: "success", title: "Invoice updated", description: "Changes were saved." });
          setEditingInvoice(null);
        },
        onError: (err) =>
          showToast({
            kind: "error",
            title: "Update failed",
            description: err instanceof ApiError ? err.message : "Something went wrong.",
          }),
      }
    );
  };

  const handleCancel = () => {
    if (!cancelTarget) return;
    cancelInvoice.mutate(cancelTarget.id, {
      onSuccess: () => showToast({ kind: "info", title: "Invoice cancelled", description: `${cancelTarget.school_name}'s invoice was cancelled.` }),
      onError: (err) =>
        showToast({
          kind: "error",
          title: "Couldn't cancel invoice",
          description: err instanceof ApiError ? err.message : "Something went wrong.",
        }),
    });
    setCancelTarget(null);
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteInvoice.mutate(
      { id: deleteTarget.id, schoolId: deleteTarget.school_id },
      {
        onSuccess: () => showToast({ kind: "info", title: "Invoice deleted", description: `${deleteTarget.school_name}'s invoice was removed.` }),
        onError: (err) =>
          showToast({
            kind: "error",
            title: "Couldn't delete invoice",
            description: err instanceof ApiError ? err.message : "Something went wrong.",
          }),
      }
    );
    setDeleteTarget(null);
  };

  return (
    <div>
      <PageHeader
        title="Invoices"
        description="500 NGN per enrolled child, billed every 30 days."
        action={
          <Button variant="outline" icon={<Download className="size-4" />} onClick={exportCsv} disabled={!invoices}>
            Export CSV
          </Button>
        }
      />

      <Card>
        <div className="border-b border-gray-100 px-4 pt-3">
          <Tabs tabs={TABS} active={tab} onChange={(k) => setTab(k as InvoiceListFilter)} />
        </div>

        {isLoading ? (
          <SkeletonTable rows={8} cols={6} />
        ) : isError ? (
          <ErrorState description="Couldn't load invoices from the API." onRetry={() => refetch()} />
        ) : !invoices || invoices.length === 0 ? (
          <EmptyState title="No invoices in this view" />
        ) : (
          <Table>
            <Thead>
              <tr>
                <Th>School</Th>
                <Th>Period</Th>
                <Th>Children</Th>
                <Th>Amount</Th>
                <Th>Status</Th>
                <Th>Due</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </Thead>
            <Tbody>
              {invoices.map((inv) => {
                const isPaid = inv.status === "paid";
                const isCancelled = inv.status === "cancelled";
                return (
                  <Tr key={inv.id}>
                    <Td
                      className="cursor-pointer font-medium text-gray-900 hover:text-brand-700"
                      onClick={() => navigate(`/schools/${inv.school_id}`)}
                    >
                      {inv.school_name}
                    </Td>
                    <Td className="text-gray-500">
                      {formatDate(inv.period_start)} – {formatDate(inv.period_end)}
                    </Td>
                    <Td>{inv.child_count}</Td>
                    <Td className="font-medium text-gray-900">{formatNaira(inv.amount_naira)}</Td>
                    <Td>
                      <Badge tone={STATUS_TONE[inv.status] ?? "gray"}>
                        {inv.status[0].toUpperCase() + inv.status.slice(1)}
                      </Badge>
                    </Td>
                    <Td className="text-gray-500">{formatDate(inv.due_date)}</Td>
                    <Td className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {!isPaid && !isCancelled && (
                          <Button
                            size="sm"
                            variant="outline"
                            icon={<Link2 className="size-3.5" />}
                            loading={createCheckoutSession.isPending}
                            onClick={() => getCheckoutLink(inv.id)}
                          >
                            Get checkout link
                          </Button>
                        )}
                        {!isPaid && (
                          <Dropdown
                            align="end"
                            trigger={
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="size-4" />
                              </Button>
                            }
                            items={[
                              { label: "Edit invoice", icon: <Pencil className="size-4" />, onClick: () => openEdit(inv) },
                              {
                                label: "Cancel invoice",
                                icon: <Ban className="size-4" />,
                                disabled: isCancelled,
                                onClick: () => setCancelTarget(inv),
                              },
                              { divider: true, label: "" },
                              {
                                label: "Delete invoice",
                                icon: <Trash2 className="size-4" />,
                                danger: true,
                                onClick: () => setDeleteTarget(inv),
                              },
                            ]}
                          />
                        )}
                      </div>
                    </Td>
                  </Tr>
                );
              })}
            </Tbody>
          </Table>
        )}
      </Card>

      <Modal
        open={editingInvoice !== null}
        onClose={() => setEditingInvoice(null)}
        title="Edit invoice"
        description={editingInvoice ? `${editingInvoice.school_name} — ${formatDate(editingInvoice.period_start)} to ${formatDate(editingInvoice.period_end)}` : undefined}
        footer={
          <>
            <Button variant="outline" onClick={() => setEditingInvoice(null)}>
              Cancel
            </Button>
            <Button loading={updateInvoice.isPending} onClick={saveEdit}>
              Save changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <Label>Children</Label>
            <Input
              type="number"
              min={0}
              value={editForm.child_count}
              onChange={(e) => setEditForm((p) => ({ ...p, child_count: e.target.value }))}
            />
          </div>
          <div>
            <Label>Amount (NGN)</Label>
            <Input
              type="number"
              min={0}
              value={editForm.amount_naira}
              onChange={(e) => setEditForm((p) => ({ ...p, amount_naira: e.target.value }))}
            />
            <p className="mt-1 text-xs text-gray-400">
              Leave as-is to recompute automatically from the children count and this school's price per child.
            </p>
          </div>
          <div>
            <Label>Due date</Label>
            <Input
              type="date"
              value={editForm.due_date}
              onChange={(e) => setEditForm((p) => ({ ...p, due_date: e.target.value }))}
            />
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={cancelTarget !== null}
        onClose={() => setCancelTarget(null)}
        onConfirm={handleCancel}
        title="Cancel this invoice?"
        description="The invoice is voided but kept on record. This can't be undone from here."
        confirmLabel="Cancel invoice"
        loading={cancelInvoice.isPending}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete this invoice?"
        description="This permanently removes the invoice record. Use Cancel instead if you want to keep it on file as voided."
        confirmLabel="Delete invoice"
        loading={deleteInvoice.isPending}
      />

      <CheckoutLinkModal url={checkoutUrl} onClose={() => setCheckoutUrl(null)} />
    </div>
  );
}
