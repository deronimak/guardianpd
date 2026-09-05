import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch, clearSession, getRole, getToken, registerUnauthorizedHandler, setSession } from "../lib/api";

interface PlatformStaffTokenResponse {
  access_token: string;
  token_type: string;
  role: string;
}

interface AuthContextValue {
  token: string | null;
  role: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getToken());
  const [role, setRole] = useState<string | null>(() => getRole());

  const logout = useCallback(() => {
    clearSession();
    setToken(null);
    setRole(null);
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(logout);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiFetch<PlatformStaffTokenResponse>("/auth/platform/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSession(response.access_token, response.role);
    setToken(response.access_token);
    setRole(response.role);
  }, []);

  return (
    <AuthContext.Provider value={{ token, role, isAuthenticated: token !== null, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
