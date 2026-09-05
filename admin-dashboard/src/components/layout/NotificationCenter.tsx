import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, AlertTriangle, Ban } from "lucide-react";
import { useSchools } from "../../api/schools";
import { useInvoices } from "../../api/invoices";
import { formatNaira } from "../../lib/format";
import { cn } from "../../lib/utils";

/** Not a persisted event feed — there's no notifications table server-side.
 * This derives a live "needs attention" list from already-fetched schools
 * and invoices data (overdue invoices, suspended schools), so it always
 * reflects real current state rather than scripted history. */
export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { data: schools } = useSchools();
  const { data: overdueInvoices } = useInvoices("overdue");

  const suspendedSchools = useMemo(
    () => (schools ?? []).filter((s) => s.subscription_status === "suspended"),
    [schools]
  );

  const alertCount = (overdueInvoices?.length ?? 0) + suspendedSchools.length;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative flex size-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
        aria-label="Notifications"
      >
        <Bell className="size-4.5" />
        {alertCount > 0 && (
          <span className="absolute right-1.5 top-1.5 flex size-2 rounded-full bg-danger-500 ring-2 ring-white" />
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-96 rounded-xl border border-gray-200 bg-white shadow-lg animate-slide-up">
            <div className="border-b border-gray-100 px-4 py-3">
              <p className="text-sm font-semibold text-gray-900">Needs attention</p>
              <p className="text-xs text-gray-500">Live status, not a notification history</p>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {alertCount === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-gray-400">Nothing needs attention.</p>
              ) : (
                <>
                  {(overdueInvoices ?? []).map((inv) => (
                    <button
                      key={inv.id}
                      onClick={() => {
                        setOpen(false);
                        navigate(`/schools/${inv.school_id}`);
                      }}
                      className={cn(
                        "flex w-full items-start gap-3 border-b border-gray-50 px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-gray-50"
                      )}
                    >
                      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-danger-50 text-danger-600">
                        <AlertTriangle className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-gray-900">Invoice overdue</span>
                        <span className="mt-0.5 block truncate text-xs text-gray-500">
                          {inv.school_name} owes {formatNaira(inv.amount_naira)}
                        </span>
                      </span>
                    </button>
                  ))}
                  {suspendedSchools.map((school) => (
                    <button
                      key={school.id}
                      onClick={() => {
                        setOpen(false);
                        navigate(`/schools/${school.id}`);
                      }}
                      className="flex w-full items-start gap-3 border-b border-gray-50 px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-gray-50"
                    >
                      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-500">
                        <Ban className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-gray-900">Subscription suspended</span>
                        <span className="mt-0.5 block truncate text-xs text-gray-500">{school.name}</span>
                      </span>
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
