import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { cn } from "../../lib/utils";

export function Table({ className, children, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full border-collapse text-sm", className)} {...props}>
        {children}
      </table>
    </div>
  );
}

export function Thead({ children }: { children: ReactNode }) {
  return <thead className="border-b border-gray-200 bg-gray-50/60">{children}</thead>;
}

export function Tbody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-gray-100">{children}</tbody>;
}

export function Tr({ className, children, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn("transition-colors duration-100 hover:bg-gray-50/80", className)} {...props}>
      {children}
    </tr>
  );
}

interface ThProps extends ThHTMLAttributes<HTMLTableCellElement> {
  sortable?: boolean;
  sortDirection?: "asc" | "desc" | null;
  onSort?: () => void;
}

export function Th({ className, children, sortable, sortDirection, onSort, ...props }: ThProps) {
  if (sortable) {
    return (
      <th className={cn("px-4 py-3 text-left text-xs font-medium text-gray-500", className)} {...props}>
        <button
          onClick={onSort}
          className="inline-flex items-center gap-1 hover:text-gray-700 focus-visible:outline-none"
        >
          {children}
          {sortDirection === "asc" ? (
            <ChevronUp className="size-3.5" />
          ) : sortDirection === "desc" ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronsUpDown className="size-3.5 text-gray-300" />
          )}
        </button>
      </th>
    );
  }
  return (
    <th className={cn("px-4 py-3 text-left text-xs font-medium text-gray-500", className)} {...props}>
      {children}
    </th>
  );
}

export function Td({ className, children, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("px-4 py-3.5 align-middle text-sm text-gray-700", className)} {...props}>
      {children}
    </td>
  );
}
