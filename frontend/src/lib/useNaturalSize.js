import { useEffect, useState } from "react";

/**
 * The pixel size of an image ({ width, height }), read by loading it — for
 * a cover photo placed before its size was kept on it. Null until known,
 * or when `src` is empty (nothing loaded then).
 */
export function useNaturalSize(src) {
  const [size, setSize] = useState(null);
  useEffect(() => {
    setSize(null);
    if (!src) return undefined;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (!cancelled && img.naturalWidth) setSize({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.src = src;
    return () => {
      cancelled = true;
    };
  }, [src]);
  return size;
}

/**
 * The pixel sizes of several images, by id ({ [id]: { width, height } }),
 * for [{ id, src }] — filled in as each one loads.
 */
export function useNaturalSizes(entries) {
  const [sizes, setSizes] = useState({});
  const key = entries.map((e) => `${e.id}|${e.src}`).join(",");
  useEffect(() => {
    let cancelled = false;
    for (const { id, src } of entries) {
      const img = new Image();
      img.onload = () => {
        if (!cancelled && img.naturalWidth) setSizes((prev) => ({ ...prev, [id]: { width: img.naturalWidth, height: img.naturalHeight } }));
      };
      img.src = src;
    }
    return () => {
      cancelled = true;
    };
    // `key` stands for the entries: a new array each render, the same images.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return sizes;
}
