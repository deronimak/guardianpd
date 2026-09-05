import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type {
  AuditLogEntry,
  School,
  SchoolDetail,
  SchoolEnrollRequest,
  SchoolUpdateRequest,
  SubscriptionUpdateRequest,
} from "../types";

const schoolsKey = (query?: string) => ["schools", query ?? ""] as const;
const schoolKey = (id: string) => ["school", id] as const;

export function useSchools(query?: string) {
  return useQuery({
    queryKey: schoolsKey(query),
    queryFn: () =>
      apiFetch<School[]>(`/platform/schools${query ? `?query=${encodeURIComponent(query)}` : ""}`),
  });
}

export function useSchool(id: string | undefined) {
  return useQuery({
    queryKey: schoolKey(id ?? ""),
    queryFn: () => apiFetch<SchoolDetail>(`/platform/schools/${id}`),
    enabled: id !== undefined,
  });
}

export function useEnrollSchool() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SchoolEnrollRequest) =>
      apiFetch<School>("/platform/schools", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schools"] }),
  });
}

export function useUpdateSchool(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SchoolUpdateRequest) =>
      apiFetch<School>(`/platform/schools/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schools"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(id) });
    },
  });
}

export function useArchiveSchool(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<School>(`/platform/schools/${id}/archive`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schools"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(id) });
    },
  });
}

export function useUnarchiveSchool(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<School>(`/platform/schools/${id}/unarchive`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schools"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(id) });
    },
  });
}

export function useDeactivateSubscription(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ status: string; subscription_status: string }>(`/platform/schools/${id}/deactivate`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schools"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(id) });
    },
  });
}

export function useReactivateSubscription(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ status: string; subscription_status: string }>(`/platform/schools/${id}/reactivate`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schools"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(id) });
    },
  });
}

export function useUpdateSubscription(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SubscriptionUpdateRequest) =>
      apiFetch<{ status: string; subscription_status: string; price_per_child_naira: number; started_at: string }>(
        `/platform/schools/${id}/subscription`,
        { method: "PATCH", body: JSON.stringify(input) }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schools"] });
      queryClient.invalidateQueries({ queryKey: schoolKey(id) });
    },
  });
}

export function useAuditLog(schoolId: string | undefined) {
  return useQuery({
    queryKey: ["audit-log", schoolId ?? ""],
    queryFn: () => apiFetch<AuditLogEntry[]>(`/platform/schools/${schoolId}/audit-log`),
    enabled: schoolId !== undefined,
  });
}
