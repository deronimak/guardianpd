import { Download, School as SchoolIcon, FileText } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { useSchools } from "../../api/schools";
import { useInvoices } from "../../api/invoices";
import { useToast } from "../../context/ToastContext";
import { downloadCsv } from "../../lib/csv";
import { formatDate } from "../../lib/format";

export function ReportsPage() {
  const { data: schools } = useSchools();
  const { data: invoices } = useInvoices("all");
  const { showToast } = useToast();

  const reports = [
    {
      key: "schools",
      icon: <SchoolIcon className="size-5" />,
      title: "Schools export",
      description: schools ? `All ${schools.length} schools with subscription status.` : "All enrolled schools.",
      disabled: !schools,
      onExport: () =>
        downloadCsv(
          "schools-report.csv",
          (schools ?? []).map((s) => ({
            ID: `GPD-${String(s.sequence_no).padStart(6, "0")}`,
            Name: s.name,
            Slug: s.slug,
            "Subscription status": s.subscription_status,
            "Billing email": s.billing_email ?? "",
            Created: formatDate(s.created_at),
          }))
        ),
    },
    {
      key: "invoices",
      icon: <FileText className="size-5" />,
      title: "Invoices export",
      description: invoices ? `All ${invoices.length} invoice${invoices.length === 1 ? "" : "s"}.` : "Every generated invoice.",
      disabled: !invoices,
      onExport: () =>
        downloadCsv(
          "invoices-report.csv",
          (invoices ?? []).map((i) => ({
            School: i.school_name,
            "Period start": formatDate(i.period_start),
            "Period end": formatDate(i.period_end),
            Children: i.child_count,
            "Amount (NGN)": i.amount_naira,
            Status: i.status,
            Due: formatDate(i.due_date),
            Paid: formatDate(i.paid_at),
          }))
        ),
    },
  ];

  const handleExport = (report: (typeof reports)[number]) => {
    report.onExport();
    showToast({ kind: "success", title: "Report exported", description: `${report.title} downloaded as CSV.` });
  };

  return (
    <div>
      <PageHeader title="Reports" description="Export school and invoice data for offline analysis." />

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {reports.map((report) => (
          <Card key={report.key}>
            <CardBody>
              <span className="flex size-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                {report.icon}
              </span>
              <h3 className="mt-3.5 text-sm font-semibold text-gray-900">{report.title}</h3>
              <p className="mt-1 text-xs text-gray-500">{report.description}</p>
              <Button
                className="mt-4"
                size="sm"
                variant="outline"
                icon={<Download className="size-3.5" />}
                disabled={report.disabled}
                onClick={() => handleExport(report)}
              >
                Export CSV
              </Button>
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}
