import { useMemo } from "react";
import { PageHeader } from "../../components/ui/PageHeader";
import { Card, CardBody } from "../../components/ui/Card";
import { Table, Thead, Tbody, Tr, Th, Td } from "../../components/ui/Table";
import { ErrorState } from "../../components/ui/EmptyState";
import { SkeletonCard } from "../../components/ui/Skeleton";
import { useInvoices } from "../../api/invoices";
import { formatNaira } from "../../lib/format";
import { RevenueByMonthChart, groupInvoicesByMonth } from "../../components/charts/RevenueByMonthChart";

export function RevenuePage() {
  const { data: invoices, isLoading, isError, refetch } = useInvoices("all");

  const monthly = useMemo(() => groupInvoicesByMonth(invoices ?? []), [invoices]);

  const bySchool = useMemo(() => {
    const totals = new Map<string, { name: string; paid: number; total: number }>();
    for (const inv of invoices ?? []) {
      if (!totals.has(inv.school_id)) totals.set(inv.school_id, { name: inv.school_name, paid: 0, total: 0 });
      const row = totals.get(inv.school_id)!;
      row.total += inv.amount_naira;
      if (inv.status === "paid") row.paid += inv.amount_naira;
    }
    return Array.from(totals.values()).sort((a, b) => b.total - a.total);
  }, [invoices]);

  const totals = useMemo(() => {
    const paid = (invoices ?? []).filter((i) => i.status === "paid").reduce((sum, i) => sum + i.amount_naira, 0);
    const pending = (invoices ?? []).filter((i) => i.status === "pending").reduce((sum, i) => sum + i.amount_naira, 0);
    const overdue = (invoices ?? []).filter((i) => i.status === "overdue").reduce((sum, i) => sum + i.amount_naira, 0);
    return { paid, pending, overdue };
  }, [invoices]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (isError) {
    return <ErrorState description="Couldn't load invoices from the API." onRetry={() => refetch()} />;
  }

  return (
    <div>
      <PageHeader title="Revenue" description="Revenue composition across every school's metered invoices." />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Collected" value={formatNaira(totals.paid, { compact: true })} tone="text-success-600" />
        <StatCard label="Pending" value={formatNaira(totals.pending, { compact: true })} tone="text-warning-600" />
        <StatCard label="Overdue" value={formatNaira(totals.overdue, { compact: true })} tone="text-danger-600" />
      </div>

      <div className="mt-6">
        <RevenueByMonthChart data={monthly} />
      </div>

      <div className="mt-6">
        <Card>
          <div className="border-b border-gray-100 px-5 py-4">
            <h3 className="text-sm font-semibold text-gray-900">Revenue by school</h3>
            <p className="text-xs text-gray-500">All-time invoiced amount, most to least</p>
          </div>
          <Table>
            <Thead>
              <tr>
                <Th>School</Th>
                <Th>Collected</Th>
                <Th>Total invoiced</Th>
              </tr>
            </Thead>
            <Tbody>
              {bySchool.map((row) => (
                <Tr key={row.name}>
                  <Td className="font-medium text-gray-900">{row.name}</Td>
                  <Td>{formatNaira(row.paid)}</Td>
                  <Td className="text-gray-500">{formatNaira(row.total)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Card>
      </div>
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <Card>
      <CardBody>
        <span className="text-xs font-medium text-gray-500">{label}</span>
        <p className={`mt-2 text-xl font-semibold tracking-tight ${tone}`}>{value}</p>
      </CardBody>
    </Card>
  );
}
