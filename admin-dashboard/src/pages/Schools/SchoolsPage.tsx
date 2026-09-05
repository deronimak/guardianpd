import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search, Download, Plus } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { Card } from "../../components/ui/Card";
import { Input, Select } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Table, Thead, Tbody, Tr, Th, Td } from "../../components/ui/Table";
import { Badge } from "../../components/ui/Badge";
import { Pagination } from "../../components/ui/Pagination";
import { EmptyState, ErrorState } from "../../components/ui/EmptyState";
import { SkeletonTable } from "../../components/ui/Skeleton";
import { useSchools } from "../../api/schools";
import { useToast } from "../../context/ToastContext";
import { formatDate } from "../../lib/format";
import { downloadCsv } from "../../lib/csv";
import { EnrollSchoolModal } from "./EnrollSchoolModal";
import type { SubscriptionStatus } from "../../types";

const PAGE_SIZE = 10;

const STATUS_OPTIONS: { value: SubscriptionStatus | "all"; label: string }[] = [
  { value: "all", label: "All subscriptions" },
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
];

export function SchoolsPage() {
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState(() => searchParams.get("query") ?? "");
  const [status, setStatus] = useState<SubscriptionStatus | "all">("all");
  const [page, setPage] = useState(1);
  const [enrollOpen, setEnrollOpen] = useState(false);

  const { data: schools, isLoading, isError, refetch } = useSchools(query);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const filtered = useMemo(() => {
    if (!schools) return [];
    if (status === "all") return schools;
    return schools.filter((s) => s.subscription_status === status);
  }, [schools, status]);

  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const exportCsv = () => {
    downloadCsv(
      "schools.csv",
      filtered.map((s) => ({
        ID: `GPD-${String(s.sequence_no).padStart(6, "0")}`,
        Name: s.name,
        Slug: s.slug,
        "Subscription status": s.subscription_status,
        Status: s.status,
        "Billing email": s.billing_email ?? "",
        Created: formatDate(s.created_at),
      }))
    );
    showToast({ kind: "success", title: "Export ready", description: `${filtered.length} schools exported to CSV.` });
  };

  return (
    <div>
      <PageHeader
        title="Schools"
        description={schools ? `${schools.length} total schools` : undefined}
        action={
          <>
            <Button variant="outline" icon={<Download className="size-4" />} onClick={exportCsv} disabled={!schools}>
              Export CSV
            </Button>
            <Button icon={<Plus className="size-4" />} onClick={() => setEnrollOpen(true)}>
              Enroll school
            </Button>
          </>
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-2.5 border-b border-gray-100 p-4">
          <div className="w-full sm:max-w-xs">
            <Input
              icon={<Search className="size-4" />}
              placeholder="Search by name, GPD-XXXXXX, phone, or email..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as SubscriptionStatus | "all");
              setPage(1);
            }}
            className="w-48"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>

        {isLoading ? (
          <SkeletonTable rows={8} cols={6} />
        ) : isError ? (
          <ErrorState description="Couldn't load schools from the API." onRetry={() => refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState title="No schools found" description="Try adjusting your search or filters." />
        ) : (
          <Table>
            <Thead>
              <tr>
                <Th>ID</Th>
                <Th>Name</Th>
                <Th>Subscription</Th>
                <Th>Status</Th>
                <Th>Billing email</Th>
                <Th>Created</Th>
              </tr>
            </Thead>
            <Tbody>
              {paged.map((school) => (
                <Tr key={school.id} className="cursor-pointer" onClick={() => navigate(`/schools/${school.id}`)}>
                  <Td className="font-mono text-xs text-gray-500">GPD-{String(school.sequence_no).padStart(6, "0")}</Td>
                  <Td className="font-medium text-gray-900">{school.name}</Td>
                  <Td>
                    <Badge tone={school.subscription_status === "active" ? "success" : "danger"}>
                      {school.subscription_status === "active" ? "Active" : "Suspended"}
                    </Badge>
                  </Td>
                  <Td>
                    <Badge tone={school.archived_at ? "gray" : "brand"}>
                      {school.archived_at ? "Archived" : school.status}
                    </Badge>
                  </Td>
                  <Td className="text-gray-500">{school.billing_email ?? "—"}</Td>
                  <Td className="text-gray-500">{formatDate(school.created_at)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}

        {!isLoading && !isError && filtered.length > 0 && (
          <Pagination page={page} pageSize={PAGE_SIZE} total={filtered.length} onPageChange={setPage} />
        )}
      </Card>

      <EnrollSchoolModal open={enrollOpen} onClose={() => setEnrollOpen(false)} />
    </div>
  );
}
