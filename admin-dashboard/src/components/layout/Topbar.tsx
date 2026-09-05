import { Menu, Search } from "lucide-react";
import { Input } from "../ui/Input";
import { NotificationCenter } from "./NotificationCenter";
import { Dropdown } from "../ui/Dropdown";
import { LogOut, Settings as SettingsIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export function Topbar({ onMenuClick, title }: { onMenuClick: () => void; title: string }) {
  const navigate = useNavigate();
  const { role, logout } = useAuth();

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    const value = (e.target as HTMLInputElement).value.trim();
    navigate(value ? `/schools?query=${encodeURIComponent(value)}` : "/schools");
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-gray-200 bg-white/80 px-4 backdrop-blur sm:px-6">
      <button
        onClick={onMenuClick}
        className="flex size-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 lg:hidden"
        aria-label="Open menu"
      >
        <Menu className="size-4.5" />
      </button>
      <h1 className="font-[var(--font-display)] text-lg font-semibold text-gray-900 lg:hidden">{title}</h1>
      <div className="hidden flex-1 max-w-md lg:block">
        <Input icon={<Search className="size-4" />} placeholder="Search schools... (press Enter)" onKeyDown={handleSearch} />
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        <NotificationCenter />
        <Dropdown
          trigger={
            <button className="flex items-center gap-2 rounded-lg p-1 pr-2 hover:bg-gray-100">
              <span className="flex size-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                {(role ?? "?").slice(0, 2).toUpperCase()}
              </span>
            </button>
          }
          items={[
            {
              label: "Settings",
              icon: <SettingsIcon className="size-4" />,
              onClick: () => navigate("/settings"),
            },
            { divider: true, label: "" },
            { label: "Sign out", icon: <LogOut className="size-4" />, danger: true, onClick: logout },
          ]}
        />
      </div>
    </header>
  );
}
