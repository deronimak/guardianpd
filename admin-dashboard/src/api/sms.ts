import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export interface SmsStatus {
  configured: boolean;
  provider: string;
  sender: string;
  balance: { total_balance: number | null; currency: string } | null;
  sender_status: { name: string; status: string } | null;
}

export interface SmsTestResult {
  ok: boolean;
  sent: boolean;
  number?: string;
  message_id?: number | string | null;
  remaining_credits?: number | null;
  cost?: number | null;
  gateway?: string | null;
  detail: string;
}

export function useSmsStatus() {
  return useQuery({ queryKey: ["sms-status"], queryFn: () => apiFetch<SmsStatus>("/platform/sms/status") });
}

export interface SmsDeliveryReport {
  summary: Record<string, number>;
  reports: { recipient: string; status: string; state: "delivered" | "pending" | "failed"; explanation: string }[];
}

export function useSmsDelivery() {
  return useMutation({
    mutationFn: (messageId: string) =>
      apiFetch<SmsDeliveryReport>(`/platform/sms/delivery/${encodeURIComponent(messageId)}`),
  });
}

export function useSendTestSms() {
  return useMutation({
    mutationFn: (to: string) =>
      apiFetch<SmsTestResult>("/platform/sms/test", { method: "POST", body: JSON.stringify({ to }) }),
  });
}
