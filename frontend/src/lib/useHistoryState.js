import { useState, useRef, useCallback } from "react";

/**
 * Like useState, but every change is undoable. Rapid successive changes
 * (e.g. every pointermove while dragging a frame, every keystroke while
 * typing) are grouped into a single history step instead of one step per
 * change, so Ctrl+Z undoes "that drag" or "that edit", not one pixel/letter
 * at a time.
 */
export function useHistoryState(initialValue) {
  const [state, setStateRaw] = useState(initialValue);
  const pastRef = useRef([]);
  const futureRef = useRef([]);
  const pendingRef = useRef(null); // pre-change snapshot waiting to be committed
  const timerRef = useRef(null);
  const GROUP_WINDOW_MS = 600;
  const MAX_HISTORY = 60;

  const flushPending = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (pendingRef.current !== null) {
      pastRef.current.push(pendingRef.current);
      if (pastRef.current.length > MAX_HISTORY) pastRef.current.shift();
      pendingRef.current = null;
    }
  }, []);

  const setState = useCallback(
    (updater) => {
      setStateRaw((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        if (next === prev) return prev;
        if (pendingRef.current === null) pendingRef.current = prev;
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(flushPending, GROUP_WINDOW_MS);
        futureRef.current = [];
        return next;
      });
    },
    [flushPending]
  );

  // Use when loading a different album (or the initial load) — the new
  // value isn't something the user should be able to "undo" back out of.
  const resetState = useCallback((newValue) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    pastRef.current = [];
    futureRef.current = [];
    pendingRef.current = null;
    setStateRaw(newValue);
  }, []);

  const undo = useCallback(() => {
    flushPending();
    if (pastRef.current.length === 0) return;
    setStateRaw((current) => {
      const previous = pastRef.current.pop();
      futureRef.current.push(current);
      return previous;
    });
  }, [flushPending]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    setStateRaw((current) => {
      const next = futureRef.current.pop();
      pastRef.current.push(current);
      return next;
    });
  }, []);

  const canUndo = () => pastRef.current.length > 0 || pendingRef.current !== null;
  const canRedo = () => futureRef.current.length > 0;

  return [state, setState, { undo, redo, canUndo, canRedo, resetState }];
}