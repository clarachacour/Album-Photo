// In-app replacement for window.confirm().
//
// window.confirm() opens the browser's own dialog, which freezes the whole
// page until it's answered (browsers report that wait as a slow interaction)
// and can't be styled or translated like the rest of the site. Usage:
//
//   const confirm = useConfirm();
//   if (await confirm({ message: t("..."), confirmLabel: t("common.delete") })) { ... }
import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const { t } = useTranslation();
  const [request, setRequest] = useState(null); // { message, confirmLabel }
  const resolveRef = useRef(null);

  const confirm = useCallback(
    ({ message, confirmLabel }) =>
      new Promise((resolve) => {
        resolveRef.current = resolve;
        setRequest({ message, confirmLabel });
      }),
    []
  );

  const answer = (value) => {
    resolveRef.current?.(value);
    resolveRef.current = null;
    setRequest(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog open={!!request} onOpenChange={(open) => !open && answer(false)}>
        <AlertDialogContent className="rounded-none sm:rounded-none bg-[color:var(--paper)] max-w-md">
          {/* The message says it all; the title only names the dialog for screen readers. */}
          <AlertDialogTitle className="sr-only">{request?.confirmLabel}</AlertDialogTitle>
          <AlertDialogDescription className="text-sm text-[color:var(--ink)] leading-relaxed">
            {request?.message}
          </AlertDialogDescription>
          <AlertDialogFooter className="gap-2 sm:space-x-0">
            <AlertDialogCancel
              onClick={() => answer(false)}
              className="rounded-none border-[color:var(--ink)]/30 text-xs font-semibold tracking-widest uppercase mt-0"
            >
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => answer(true)}
              className="rounded-none bg-[color:var(--ink)] text-[color:var(--paper)] hover:bg-[color:var(--ink)]/90 text-xs font-semibold tracking-widest uppercase"
            >
              {request?.confirmLabel || t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm must be used inside <ConfirmProvider>");
  return confirm;
}
