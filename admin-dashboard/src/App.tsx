import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "./context/ToastContext";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { AppLayout } from "./components/layout/AppLayout";
import { LoginPage } from "./pages/Login/LoginPage";
import { OverviewPage } from "./pages/Overview/OverviewPage";
import { SchoolsPage } from "./pages/Schools/SchoolsPage";
import { SchoolDetailPage } from "./pages/Schools/SchoolDetailPage";
import { InvoicesPage } from "./pages/Invoices/InvoicesPage";
import { RevenuePage } from "./pages/Revenue/RevenuePage";
import { ReportsPage } from "./pages/Reports/ReportsPage";
import { SettingsPage } from "./pages/Settings/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter basename="/admin">
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                element={
                  <RequireAuth>
                    <AppLayout />
                  </RequireAuth>
                }
              >
                <Route path="/" element={<OverviewPage />} />
                <Route path="/schools" element={<SchoolsPage />} />
                <Route path="/schools/:schoolId" element={<SchoolDetailPage />} />
                <Route path="/invoices" element={<InvoicesPage />} />
                <Route path="/revenue" element={<RevenuePage />} />
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
