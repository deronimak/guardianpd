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
import { useSendTestSms, useSmsDelivery, useSmsStatus } from "../../api/sms";
import { usePushStatus, useSendTestPush, type PushTestResult } from "../../api/push";

export function SettingsPage() {
  const { role, logout } = useAuth();
  const { showToast } = useToast();
  const changePassword = useChangePassword();
  const smsStatus = useSmsStatus();
  const sendTestSms = useSendTestSms();
  const smsDelivery = useSmsDelivery();
  const [lastMessageId, setLastMessageId] = useState<string | null>(null);
  const [deliveryText, setDeliveryText] = useState<string | null>(null);
  const pushStatus = usePushStatus();
  const sendTestPush = useSendTestPush();
  const [pushEmail, setPushEmail] = useState("");
  const [pushResult, setPushResult] = useState<PushTestResult | null>(null);
  const [pushError, setPushError] = useState<string | null>(null);
  const [testNumber, setTestNumber] = useState("");
  const [smsMessage, setSmsMessage] = useState<{ ok: boolean; text: string } | null>(null);

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
          <CardHeader
            title="SMS alerts"
            description="Texts parents who don't use the app. Send a test message to confirm SMS works before switching it on for a school."
          />
          <CardBody className="space-y-4">
            <div className="flex items-center justify-between text-sm text-gray-600">
              <span>SMS provider ({smsStatus.data?.provider === "brevo" ? "Brevo" : "BulkSMSNigeria"})</span>
              {smsStatus.data ? (
                <Badge tone={smsStatus.data.configured ? "brand" : "gray"}>
                  {smsStatus.data.configured
                    ? `Configured (sender: ${smsStatus.data.sender}${
                        smsStatus.data.balance?.total_balance != null
                          ? ` · balance: ₦${smsStatus.data.balance.total_balance.toLocaleString()}`
                          : ""
                      })`
                    : "Not configured"}
                </Badge>
              ) : null}
            </div>
            {smsStatus.data?.sender_status && (
              <div className="flex items-center justify-between text-sm text-gray-600">
                <span>Sender name “{smsStatus.data.sender_status.name}”</span>
                <Badge tone={smsStatus.data.sender_status.status.toLowerCase() === "approved" ? "brand" : "gray"}>
                  {smsStatus.data.sender_status.status}
                </Badge>
              </div>
            )}
            <div>
              <Label>Send a test SMS to</Label>
              <Input placeholder="08012345678" value={testNumber} onChange={(e) => setTestNumber(e.target.value)} />
            </div>
            {lastMessageId && (
              <div className="space-y-1.5">
                <Button
                  variant="secondary"
                  loading={smsDelivery.isPending}
                  onClick={() => {
                    setDeliveryText(null);
                    smsDelivery.mutate(lastMessageId, {
                      onSuccess: (r) =>
                        setDeliveryText(
                          r.reports.length
                            ? r.reports.map((x) => `${x.recipient}: ${x.explanation}`).join(" | ")
                            : "No delivery information yet. Try again in a minute."
                        ),
                      onError: (err) => setDeliveryText(err instanceof ApiError ? err.message : "Something went wrong."),
                    });
                  }}
                >
                  Check delivery status
                </Button>
                {deliveryText && <p className="text-xs font-medium text-gray-700">{deliveryText}</p>}
              </div>
            )}
            {smsMessage && (
              <p className={`text-xs font-medium ${smsMessage.ok ? "text-gray-700" : "text-danger-600"}`}>{smsMessage.text}</p>
            )}
          </CardBody>
          <div className="flex justify-end border-t border-gray-100 px-5 py-4">
            <Button
              loading={sendTestSms.isPending}
              disabled={!testNumber.trim()}
              onClick={() => {
                setSmsMessage(null);
                setLastMessageId(null);
                setDeliveryText(null);
                sendTestSms.mutate(testNumber.trim(), {
                  onSuccess: (r) => {
                    if (r.message_id) setLastMessageId(String(r.message_id));
                    return
                    setSmsMessage({
                      ok: true,
                      text: r.sent
                        ? `Sent to ${r.number}.${r.remaining_credits != null ? ` Credits left: ${r.remaining_credits}.` : ""}${r.cost != null ? ` Cost: ₦${r.cost}.` : ""}`
                        : r.detail,
                    });
                  },
                  onError: (err) => setSmsMessage({ ok: false, text: err instanceof ApiError ? err.message : "Something went wrong." }),
                });
              }}
            >
              Send test SMS
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Push notifications"
            description="Send a real test notification to every phone a parent has registered, and see exactly what Firebase answers for each one. Use this to check a new iPhone."
          />
          <CardBody className="space-y-4">
            <div className="flex items-center justify-between text-sm text-gray-600">
              <span>Firebase on the server</span>
              {pushStatus.data ? (
                <Badge tone={pushStatus.data.configured ? "brand" : "gray"}>
                  {pushStatus.data.configured ? "Configured" : "Not configured"}
                </Badge>
              ) : null}
            </div>
            <div>
              <Label>Parent's email</Label>
              <Input placeholder="parent@example.com" value={pushEmail} onChange={(e) => setPushEmail(e.target.value)} />
            </div>
            {pushError && <p className="text-xs font-medium text-danger-600">{pushError}</p>}
            {pushResult && (
              <ul className="space-y-1.5 text-xs text-gray-700">
                {pushResult.devices.map((d) => (
                  <li key={d.token_tail + d.school} className={d.ok ? "" : "font-medium text-danger-600"}>
                    {d.ok ? "OK" : "FAILED"} · {d.school} · registered as {d.registered_as} · ...{d.token_tail} · {d.detail}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
          <div className="flex justify-end border-t border-gray-100 px-5 py-4">
            <Button
              loading={sendTestPush.isPending}
              disabled={!pushEmail.trim()}
              onClick={() => {
                setPushError(null);
                setPushResult(null);
                sendTestPush.mutate(pushEmail.trim(), {
                  onSuccess: (r) => setPushResult(r),
                  onError: (err) => setPushError(err instanceof ApiError ? err.message : "Something went wrong."),
                });
              }}
            >
              Send test notification
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
