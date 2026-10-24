// A paid action's confirm step, built into the page (P5-8): never a browser dialog.

import { useState } from "react";

type Props = {
  label: string;
  question: string;
  onConfirm: () => void;
  disabled?: boolean;
};

export function ConfirmInline({
  label,
  question,
  onConfirm,
  disabled = false,
}: Props) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button type="button" disabled={disabled} onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <span className="confirm-inline">
      <span>{question}</span>
      <button
        type="button"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        Confirm
      </button>
      <button type="button" onClick={() => setAsking(false)}>
        Cancel
      </button>
    </span>
  );
}
