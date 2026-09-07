"use client";

import * as React from "react";
import dynamic from "next/dynamic";

// Deferred so pages that never ask for a confirmation don't pay for the dialog.
const ConfirmDialogImpl = dynamic(() => import("@/components/ui/confirm-dialog-impl"), {
  ssr: false,
});

const ConfirmContext = React.createContext(null);

const DEFAULTS = {
  title: "Confirm action",
  description: "",
  confirmLabel: "Confirm",
  cancelLabel: "Cancel",
  variant: "destructive",
};

/**
 * Provides an async confirm() that resolves true/false, replacing window.confirm.
 * Mount once near the root; read it with useConfirm().
 */
export function ConfirmProvider({ children }) {
  const [options, setOptions] = React.useState(DEFAULTS);
  const [open, setOpen] = React.useState(false);
  const [everOpened, setEverOpened] = React.useState(false);
  const resolverRef = React.useRef(null);

  const confirm = React.useCallback((opts) => {
    setOptions({ ...DEFAULTS, ...(typeof opts === "string" ? { description: opts } : opts) });
    setEverOpened(true);
    setOpen(true);
    return new Promise((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  // Options are kept after closing so the exit animation doesn't render an empty box.
  const settle = React.useCallback((result) => {
    setOpen(false);
    const resolve = resolverRef.current;
    resolverRef.current = null;
    resolve?.(result);
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {everOpened ? (
        <ConfirmDialogImpl open={open} options={options} onSettle={settle} />
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const confirm = React.useContext(ConfirmContext);
  if (!confirm) {
    throw new Error("useConfirm must be used inside a ConfirmProvider");
  }
  return confirm;
}
