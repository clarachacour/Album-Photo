import { toast } from "sonner";

// A confirmation message that must survive a full page reload (e.g. after
// deleting the account): stored for the next load, shown once by App.
const KEY = "everbook_flash";

export function showAfterReload(message) {
  try {
    sessionStorage.setItem(KEY, message);
  } catch {
    /* storage unavailable: no message */
  }
}

export function showPendingFlash() {
  try {
    const message = sessionStorage.getItem(KEY);
    if (message) {
      sessionStorage.removeItem(KEY);
      toast.success(message);
    }
  } catch {
    /* storage unavailable */
  }
}
