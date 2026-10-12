import { useEffect } from "react";

// Where a click keeps the current selection: the book itself (its own
// clicks already select/deselect), toolbars, the settings panels, dialogs
// and the guide. Anything else on the page deselects.
export const KEEP_SELECTION =
  '[data-book-sheet], [data-tour="cover-spread"], [data-tour="cover-panel"], [data-item-toolbar], [data-tour="page-tools"], aside, [role="dialog"], [role="alertdialog"], [data-testid="guided-tour"], [data-sonner-toaster], [data-keep-selection]';

/** While something is selected (`active`), a click anywhere outside the
 * places above — or Escape — calls `onDeselect`. */
export function useDeselectOutside(active, onDeselect) {
  useEffect(() => {
    if (!active) return;
    const onDown = (e) => {
      if (e.target instanceof Element && e.target.closest(KEEP_SELECTION)) return;
      onDeselect();
    };
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || document.activeElement?.isContentEditable) return;
      onDeselect();
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [active, onDeselect]);
}
