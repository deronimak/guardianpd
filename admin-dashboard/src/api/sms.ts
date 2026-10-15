import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export interface SmsStatus {
  configured: boolean;
  sender: string;
}

export interface SmsTestResult {
  ok: boolean;
  sent: boolean;
  number?: string;
  message_id?: number | string | null;
  remaining_credits?: number | null;
  detail: string;
}

export function useSmsStatus() {
  return useQuery({ queryKey: ["sms-status"], queryFn: () => apiFetch<SmsStatus>("/platform/sms/status") });
}

export function useSendTestSms() {
  return useMutation({
    mutationFn: (to: string) =>
      apiFetch<SmsTestResult>("/platform/sms/test", { method: "POST", body: JSON.stringify({ to }) }),
  });
}
