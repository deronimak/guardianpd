import { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Input, Label } from "../../components/ui/Input";
import { useEnrollSchool } from "../../api/schools";
import { useToast } from "../../context/ToastContext";
import { ApiError } from "../../lib/api";

const emptyForm = {
  name: "",
  slug: "",
  address: "",
  phone: "",
  admin_name: "",
  admin_email: "",
  admin_temp_password: "",
  timezone: "UTC",
  billing_email: "",
};

export function EnrollSchoolModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const enrollSchool = useEnrollSchool();
  const { showToast } = useToast();
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const set = (field: keyof typeof emptyForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const reset = () => {
    setForm(emptyForm);
    setError(null);
  };

  const handleSubmit = () => {
    setError(null);
    if (!form.name.trim() || !form.slug.trim() || !form.address.trim() || !form.phone.trim()) {
      setError("Name, slug, address and phone are required.");
      return;
    }
    if (!form.admin_name.trim() || !form.admin_email.trim() || form.admin_temp_password.length < 8) {
      setError("Admin name, email and a temporary password (min 8 characters) are required.");
      return;
    }
    enrollSchool.mutate(
      {
        name: form.name.trim(),
        slug: form.slug.trim(),
        address: form.address.trim(),
        phone: form.phone.trim(),
        admin_name: form.admin_name.trim(),
        admin_email: form.admin_email.trim(),
        admin_temp_password: form.admin_temp_password,
        timezone: form.timezone.trim() || "UTC",
        billing_email: form.billing_email.trim() || undefined,
      },
      {
        onSuccess: (school) => {
          showToast({ kind: "success", title: "School enrolled", description: `${school.name} was enrolled.` });
          reset();
          onClose();
        },
        onError: (err) => {
          setError(err instanceof ApiError ? err.message : "Failed to enroll school.");
        },
      }
    );
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Enroll school"
      description="Provision a new school and its first School Admin account."
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={enrollSchool.isPending}>
            Enroll school
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label>School name</Label>
          <Input placeholder="Fieldstone Academy" value={form.name} onChange={set("name")} />
        </div>
        <div>
          <Label>Slug</Label>
          <Input placeholder="fieldstone-academy" value={form.slug} onChange={set("slug")} />
        </div>
        <div>
          <Label>Timezone</Label>
          <Input placeholder="Africa/Lagos" value={form.timezone} onChange={set("timezone")} />
        </div>
        <div>
          <Label>Address</Label>
          <Input placeholder="12 School Rd, Lagos" value={form.address} onChange={set("address")} />
        </div>
        <div>
          <Label>Phone</Label>
          <Input placeholder="+234 800 000 0000" value={form.phone} onChange={set("phone")} />
        </div>
        <div className="sm:col-span-2">
          <Label>Billing email (optional — defaults to admin email)</Label>
          <Input type="email" placeholder="billing@fieldstone.edu" value={form.billing_email} onChange={set("billing_email")} />
        </div>
        <div className="sm:col-span-2 border-t border-gray-100 pt-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">First School Admin</p>
        </div>
        <div>
          <Label>Admin name</Label>
          <Input placeholder="Jordan Blake" value={form.admin_name} onChange={set("admin_name")} />
        </div>
        <div>
          <Label>Admin email</Label>
          <Input type="email" placeholder="admin@fieldstone.edu" value={form.admin_email} onChange={set("admin_email")} />
        </div>
        <div className="sm:col-span-2">
          <Label>Temporary password (min 8 characters)</Label>
          <Input type="text" value={form.admin_temp_password} onChange={set("admin_temp_password")} />
        </div>
        {error && <p className="sm:col-span-2 text-xs font-medium text-danger-600">{error}</p>}
      </div>
    </Modal>
  );
}
