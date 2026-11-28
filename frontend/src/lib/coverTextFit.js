import { useSyncExternalStore } from "react";

// The size each cover text is really drawn at in the editor (a text too
// big for its box is drawn smaller, see AutoFitText), by item id: the Size
// slider shows it instead of the asked size.
const sizes = new Map();
const listeners = new Set();

export function setFittedSize(itemId, px) {
  if (sizes.get(itemId) === px) return;
  sizes.set(itemId, px);
  listeners.forEach((l) => l());
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useFittedSize(itemId) {
  return useSyncExternalStore(subscribe, () => (itemId ? sizes.get(itemId) : undefined), () => undefined);
}
