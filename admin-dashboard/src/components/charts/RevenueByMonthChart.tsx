import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Invoice } from "../../types";
import { formatNaira } from "../../lib/format";

export interface MonthlyRevenuePoint {
  month: string;
  paid: number;
  pending: number;
  overdue: number;
}

/** Groups invoices by the calendar month their billing period started in —
 * the natural granularity for 30-day metered cycles, unlike a daily series
 * which doesn't exist for this data. */
export function groupInvoicesByMonth(invoices: Invoice[]): MonthlyRevenuePoint[] {
  const byMonth = new Map<string, MonthlyRevenuePoint>();
  for (const inv of invoices) {
    const month = inv.period_start.slice(0, 7); // "YYYY-MM"
    if (!byMonth.has(month)) byMonth.set(month, { month, paid: 0, pending: 0, overdue: 0 });
    const point = byMonth.get(month)!;
    if (inv.status === "paid") point.paid += inv.amount_naira;
    else if (inv.status === "overdue") point.overdue += inv.amount_naira;
    else point.pending += inv.amount_naira;
  }
  return Array.from(byMonth.values()).sort((a, b) => a.month.localeCompare(b.month));
}

function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return new Date(Number(year), Number(m) - 1, 1).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export function RevenueByMonthChart({ data }: { data: MonthlyRevenuePoint[] }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs">
      <h3 className="text-sm font-semibold text-gray-900">Revenue by billing month</h3>
      <p className="text-xs text-gray-500">Invoiced amount per 30-day cycle, across all schools</p>
      <div className="mt-5 h-72 w-full">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-400">No invoices yet</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#eaecf0" />
              <XAxis
                dataKey="month"
                tickFormatter={monthLabel}
                tick={{ fontSize: 11, fill: "#98a2b3" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tickFormatter={(v) => formatNaira(v, { compact: true })}
                tick={{ fontSize: 11, fill: "#98a2b3" }}
                tickLine={false}
                axisLine={false}
                width={64}
              />
              <Tooltip
                formatter={((v: number) => formatNaira(v)) as any}
                labelFormatter={(m) => monthLabel(m as string)}
                contentStyle={{
                  borderRadius: 8,
                  border: "1px solid #e4e7ec",
                  fontSize: 12,
                  boxShadow: "0 4px 12px rgba(16,24,40,0.08)",
                }}
              />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "#667085", paddingTop: 12 }} />
              <Bar dataKey="paid" name="Paid" stackId="a" fill="#12b76a" radius={[0, 0, 0, 0]} />
              <Bar dataKey="pending" name="Pending" stackId="a" fill="#f79009" radius={[0, 0, 0, 0]} />
              <Bar dataKey="overdue" name="Overdue" stackId="a" fill="#f04438" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
