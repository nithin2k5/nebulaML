"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

/**
 * Rendered half of the confirm dialog. Split from the provider so the Radix
 * dialog is only fetched once something actually asks for a confirmation.
 */
export default function ConfirmDialogImpl({ open, options, onSettle }) {
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onSettle(false); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{options.title}</DialogTitle>
          {options.description ? (
            <DialogDescription>{options.description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onSettle(false)}>
            {options.cancelLabel}
          </Button>
          <Button variant={options.variant} onClick={() => onSettle(true)} autoFocus>
            {options.confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
