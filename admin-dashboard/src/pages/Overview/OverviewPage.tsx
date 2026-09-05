import { useMemo } from "react";
import { School as SchoolIcon, Ban, Wallet, AlertTriangle } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { KpiCard } from "../../components/ui/KpiCard";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { SkeletonCard } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/EmptyState";
import { useSchools } from "../../api/schools";
import { useInvoices } from "../../api/invoices";
import { formatNaira, formatNumber } from "../../lib/format";
import { RevenueByMonthChart, groupInvoicesByMonth } from "../../components/charts/RevenueByMonthChart";

export function OverviewPage() {
  const { data: schools, isLoading: schoolsLoading, isError: schoolsError, refetch: refetchSchools } = useSchools();
  const { data: invoices, isLoading: invoicesLoading, isError: invoicesError, refetch: refetchInvoices } = useInvoices("all");

  const isLoading = schoolsLoading || invoicesLoading;
  const isError = schoolsError || invoicesError;

  const stats = useMemo(() => {
    const activeSchools = schools?.filter((s) => s.subscription_status === "active").length ?? 0;
    const suspendedSchools = schools?.filter((s) => s.subscription_status === "suspended").length ?? 0;
    const revenueCollected = invoices?.filter((i) => i.status === "paid").reduce((sum, i) => sum + i.amount_naira, 0) ?? 0;
    const amountOverdue = invoices?.filter((i) => i.status === "overdue").reduce((sum, i) => sum + i.amount_naira, 0) ?? 0;
    return { activeSchools, suspendedSchools, revenueCollected, amountOverdue };
  }, [schools, invoices]);

  const monthly = useMemo(() => groupInvoicesByMonth(invoices ?? []), [invoices]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        description="Couldn't load schools or invoices from the API."
        onRetry={() => {
          refetchSchools();
          refetchInvoices();
        }}
      />
    );
  }

  return (
    <div>
      <PageHeader title="Overview" description="GuardianPD's schools and billing at a glance." />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Total schools" value={formatNumber(schools?.length ?? 0)} icon={<SchoolIcon className="size-4" />} subtext="enrolled" />
        <KpiCard label="Active subscriptions" value={formatNumber(stats.activeSchools)} icon={<SchoolIcon className="size-4" />} subtext={`${stats.suspendedSchools} suspended`} />
        <KpiCard label="Revenue collected" value={formatNaira(stats.revenueCollected, { compact: true })} icon={<Wallet className="size-4" />} subtext="all paid invoices" />
        <KpiCard label="Overdue amount" value={formatNaira(stats.amountOverdue, { compact: true })} icon={<AlertTriangle className="size-4" />} subtext="past due + grace period" />
      </div>

      <div className="mt-6">
        <RevenueByMonthChart data={monthly} />
      </div>

      {stats.suspendedSchools > 0 && (
        <div className="mt-6">
          <Card>
            <CardHeader title="Suspended schools" description="These schools cannot scan or issue QR codes right now" />
            <CardBody className="flex items-center gap-2.5 text-sm text-gray-600">
              <Ban className="size-4 text-danger-500" />
              {stats.suspendedSchools} school{stats.suspendedSchools === 1 ? "" : "s"} currently suspended — see the Schools page to reactivate.
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
