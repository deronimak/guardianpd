import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export interface PushStatus {
  configured: boolean;
}

export interface PushTestDevice {
  school: string;
  registered_as: string;
  token_tail: string;
  ok: boolean;
  detail: string;
}

export interface PushTestResult {
  email: string;
  firebase_configured: boolean;
  devices: PushTestDevice[];
}

export function usePushStatus() {
  return useQuery({ queryKey: ["push-status"], queryFn: () => apiFetch<PushStatus>("/platform/push/status") });
}

export function useSendTestPush() {
  return useMutation({
    mutationFn: (email: string) =>
      apiFetch<PushTestResult>("/platform/push/test", { method: "POST", body: JSON.stringify({ email }) }),
  });
}
