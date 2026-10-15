import { createContext, useContext } from "react";

// What a page editing an album offers to try a change out without adding
// it to the undo history (see useHistoryState's withoutHistory): hovering
// a font in a list shows it on the text, and only the click counts.
export const HistoryPreviewContext = createContext((fn) => fn());

export function useWithoutHistory() {
  return useContext(HistoryPreviewContext);
}
