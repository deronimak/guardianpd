import { Modal } from "./Modal";
import { Button } from "./Button";

export function CheckoutLinkModal({
  url,
  onClose,
}: {
  url: string | null;
  onClose: () => void;
}) {
  return (
    <Modal
      open={url !== null}
      onClose={onClose}
      title="Checkout link"
      description="Share this Paystack link with the school to collect payment."
      footer={
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      }
    >
      <p className="break-all rounded-lg bg-gray-50 p-3 font-mono text-xs text-gray-700">{url}</p>
    </Modal>
  );
}
