// Dialogs (STYLEGUIDE §4.5, §6.3): white panel, radius 16, e3 shadow; footer actions with the primary on the right and
// the secondary 12px to its left (full width and stacked on phones). Focus is trapped and restored by Radix.
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const overlay = "fixed inset-0 z-50 bg-ink-900/40";
const panel =
  "fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-32px)] w-[calc(100vw-32px)] max-w-[520px] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 " +
  "overflow-y-auto rounded-lg border border-slate-100 bg-white p-6 shadow-e3 focus-visible:shadow-e3 sm:p-8";
const titleCls = "m-0 pr-10 text-h3 font-semibold text-slate-900";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;

export function DialogContent({ className, children, title, description, ...props }:
  React.ComponentProps<typeof DialogPrimitive.Content> & { title: string; description?: React.ReactNode }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className={overlay} />
      <DialogPrimitive.Content className={cn(panel, className)} {...props}>
        <DialogPrimitive.Title className={titleCls}>{title}</DialogPrimitive.Title>
        {description ? (
          <DialogPrimitive.Description className="m-0 text-body text-slate-600">{description}</DialogPrimitive.Description>
        ) : (
          <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
        )}
        <div className="min-w-0">{children}</div>
        <DialogPrimitive.Close asChild>
          <Button variant="tertiary" size="icon-sm" className="absolute right-4 top-4 text-slate-600" aria-label="Close" data-tooltip="Close">
            <X aria-hidden />
          </Button>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogFooter({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex flex-col-reverse gap-3 sm:flex-row sm:justify-end [&>*]:w-full sm:[&>*]:w-auto", className)}>{children}</div>;
}

/** Confirmation dialog for consequential actions (publish, submit, delete, replace ...). */
export function ConfirmDialog({
  open, onOpenChange, title, description, confirmLabel, cancelLabel = "Cancel", onConfirm, loading, loadingLabel, tone = "primary", children,
  confirmDisabled,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  loading?: boolean;
  loadingLabel?: string;
  tone?: "primary" | "destructive";
  children?: React.ReactNode;
  confirmDisabled?: boolean;
}) {
  return (
    <AlertDialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Overlay className={overlay} />
        <AlertDialogPrimitive.Content className={panel}>
          <AlertDialogPrimitive.Title className={titleCls}>{title}</AlertDialogPrimitive.Title>
          <AlertDialogPrimitive.Description asChild>
            <div className="flex flex-col gap-2 text-body text-slate-600 [&_p]:m-0">{description}</div>
          </AlertDialogPrimitive.Description>
          {children}
          <DialogFooter className="pt-2">
            <AlertDialogPrimitive.Cancel asChild>
              <Button variant="secondary" disabled={loading}>{cancelLabel}</Button>
            </AlertDialogPrimitive.Cancel>
            <Button variant={tone === "destructive" ? "destructive" : "primary"} loading={loading} loadingLabel={loadingLabel}
              disabled={confirmDisabled} onClick={onConfirm}>{confirmLabel}</Button>
          </DialogFooter>
        </AlertDialogPrimitive.Content>
      </AlertDialogPrimitive.Portal>
    </AlertDialogPrimitive.Root>
  );
}
