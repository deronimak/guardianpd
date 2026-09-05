import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { Invoice, InvoiceListFilter, InvoiceUpdateRequest, ManualInvoiceResult } from "../types";

export function useInvoices(status: InvoiceListFilter, schoolId?: string) {
  return useQuery({
    queryKey: ["invoices", status, schoolId ?? ""],
    queryFn: () => {
      const params = new URLSearchParams({ status });
      if (schoolId) params.set("school_id", schoolId);
      return apiFetch<Invoice[]>(`/platform/invoices?${params.toString()}`);
    },
  });
}

export function useCreateCheckoutSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invoiceId: string) =>
      apiFetch<{ checkout_url: string }>(`/platform/invoices/${invoiceId}/checkout-session`, {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invoices"] }),
  });
}

export function useCreateManualInvoice(schoolId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ManualInvoiceResult>(`/platform/schools/${schoolId}/invoices`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(schoolId) });
    },
  });
}

export function useUpdateInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: InvoiceUpdateRequest }) =>
      apiFetch<Invoice>(`/platform/invoices/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
    onSuccess: (invoice) => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(invoice.school_id) });
    },
  });
}

export function useCancelInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invoiceId: string) => apiFetch<Invoice>(`/platform/invoices/${invoiceId}/cancel`, { method: "POST" }),
    onSuccess: (invoice) => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(invoice.school_id) });
    },
  });
}

export function useDeleteInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string; schoolId: string }) =>
      apiFetch<void>(`/platform/invoices/${id}`, { method: "DELETE" }),
    onSuccess: (_data, { schoolId }) => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(schoolId) });
    },
  });
}

function schoolKey(id: string) {
  return ["school", id] as const;
}
