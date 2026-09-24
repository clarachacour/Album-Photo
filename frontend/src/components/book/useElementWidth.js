import { useState, useEffect } from "react";

/** Tracks an element's live pixel width via ResizeObserver. */
export function useElementWidth(ref) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.unobserve(el);
  }, [ref]);
  return width;
}
