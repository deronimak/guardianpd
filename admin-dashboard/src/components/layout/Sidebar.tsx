import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  School,
  FileText,
  LineChart,
  BarChart3,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { cn } from "../../lib/utils";

const NAV_GROUPS = [
  {
    label: "General",
    items: [{ to: "/", label: "Overview", icon: LayoutDashboard, end: true }],
  },
  {
    label: "Billing",
    items: [
      { to: "/schools", label: "Schools", icon: School },
      { to: "/invoices", label: "Invoices", icon: FileText },
    ],
  },
  {
    label: "Insights",
    items: [
      { to: "/revenue", label: "Revenue", icon: LineChart },
      { to: "/reports", label: "Reports", icon: BarChart3 },
    ],
  },
  {
    label: "Configuration",
    items: [{ to: "/settings", label: "Settings", icon: Settings }],
  },
];

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="px-2.5 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            {group.label}
          </p>
          <div className="space-y-0.5">
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={"end" in item ? item.end : false}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-brand-50 text-brand-700"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  )
                }
              >
                <item.icon className="size-4 shrink-0" />
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-gray-200 bg-white lg:flex">
      <div className="flex h-16 items-center border-b border-gray-100 px-5">
        <Brand />
      </div>
      <NavItems />
      <PlanFooter />
    </aside>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-lg bg-brand-600 text-white">
        <ShieldCheck className="size-4.5" />
      </span>
      <span className="font-[var(--font-display)] text-[15px] font-bold text-gray-900">GuardianPD</span>
    </div>
  );
}

function PlanFooter() {
  return (
    <div className="border-t border-gray-100 p-3">
      <div className="rounded-lg bg-gray-50 px-3 py-2.5">
        <p className="text-xs font-medium text-gray-700">GuardianPD Admin</p>
        <p className="text-[11px] text-gray-400">v1.0.0 &middot; Production</p>
      </div>
    </div>
  );
}

export function MobileSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex lg:hidden">
      <div className="absolute inset-0 bg-gray-900/40 animate-fade-in" onClick={onClose} />
      <div className="relative flex h-full w-72 flex-col bg-white shadow-xl animate-slide-in-right">
        <div className="flex h-16 items-center justify-between border-b border-gray-100 px-5">
          <Brand />
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100">
            <X className="size-4" />
          </button>
        </div>
        <NavItems onNavigate={onClose} />
        <PlanFooter />
      </div>
    </div>
  );
}
