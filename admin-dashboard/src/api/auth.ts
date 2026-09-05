import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (input: ChangePasswordInput) =>
      apiFetch<{ status: string }>("/auth/platform/change-password", {
        method: "POST",
        body: JSON.stringify(input),
        // A 401 here means "current password is incorrect", not "your
        // session expired" — don't force a logout/redirect for it.
        skipUnauthorizedHandler: true,
      }),
  });
}
