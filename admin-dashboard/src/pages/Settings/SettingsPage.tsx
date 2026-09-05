import { useState } from "react";
import { PageHeader } from "../../components/ui/PageHeader";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input, Label } from "../../components/ui/Input";
import { Badge } from "../../components/ui/Badge";
import { useAuth } from "../../context/AuthContext";
import { useChangePassword } from "../../api/auth";
import { useToast } from "../../context/ToastContext";
import { ApiError } from "../../lib/api";

export function SettingsPage() {
  const { role, logout } = useAuth();
  const { showToast } = useToast();
  const changePassword = useChangePassword();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = () => {
    setError(null);
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match.");
      return;
    }
    changePassword.mutate(
      { current_password: currentPassword, new_password: newPassword },
      {
        onSuccess: () => {
          showToast({ kind: "success", title: "Password updated", description: "Your password was changed." });
          setCurrentPassword("");
          setNewPassword("");
          setConfirmPassword("");
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong."),
      }
    );
  };

  return (
    <div>
      <PageHeader title="Settings" description="Manage your Master Admin account." />

      <div className="max-w-xl space-y-6">
        <Card>
          <CardHeader title="Account" description="Signed in as a platform staff member" />
          <CardBody className="flex items-center justify-between">
            <span className="text-sm text-gray-600">Role</span>
            <Badge tone="brand">{role ?? "unknown"}</Badge>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Change password" />
          <CardBody className="space-y-4">
            <div>
              <Label>Current password</Label>
              <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
            </div>
            <div>
              <Label>New password</Label>
              <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            </div>
            <div>
              <Label>Confirm new password</Label>
              <Input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            </div>
            {error && <p className="text-xs font-medium text-danger-600">{error}</p>}
          </CardBody>
          <div className="flex justify-end border-t border-gray-100 px-5 py-4">
            <Button onClick={handleSubmit} loading={changePassword.isPending}>
              Update password
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader title="Sign out" description="End your current session on this device" />
          <CardBody>
            <Button variant="dangerGhost" onClick={logout}>
              Sign out
            </Button>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
