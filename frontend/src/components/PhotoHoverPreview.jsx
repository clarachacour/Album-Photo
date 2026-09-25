import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { photoImageUrl } from "@/lib/api";

const SIZE = 320; // px, longest side of the preview
const DELAY_MS = 180; // skip photos the mouse only crosses on its way

/**
 * Larger, uncropped preview of a small photo thumbnail while the mouse rests
 * on it — to tell apart photos that look alike at thumbnail size.
 *
 *   const preview = usePhotoHoverPreview();
 *   <div {...preview.bind(photoId)}>…thumbnail…</div>
 *   {preview.element}
 *
 * Mouse only: on a touch screen a tap would open it with nothing to close it.
 * Call preview.hide() when a drag starts.
 */
export function usePhotoHoverPreview() {
  const [preview, setPreview] = useState(null); // { photoId, rect }
  const timer = useRef(null);

  const hide = useCallback(() => {
    clearTimeout(timer.current);
    setPreview(null);
  }, []);

  useEffect(() => {
    // The preview is positioned once; scrolling would leave it behind.
    window.addEventListener("scroll", hide, true);
    return () => {
      window.removeEventListener("scroll", hide, true);
      clearTimeout(timer.current);
    };
  }, [hide]);

  const bind = (photoId) => ({
    onPointerEnter: (e) => {
      if (e.pointerType !== "mouse" || e.buttons) return;
      const rect = e.currentTarget.getBoundingClientRect();
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setPreview({ photoId, rect }), DELAY_MS);
    },
    // No onPointerDown here: it would replace the drag-and-drop library's
    // own handler on sortable thumbnails. Callers hide it when a drag starts.
    onPointerLeave: hide,
  });

  const element = preview ? createPortal(<PreviewBox {...preview} />, document.body) : null;
  return { bind, hide, element };
}

function PreviewBox({ photoId, rect }) {
  const margin = 8;
  // Above the thumbnail when there's room, otherwise below; kept on screen.
  const above = rect.top > SIZE + margin * 2;
  const top = above ? rect.top - SIZE - margin : rect.bottom + margin;
  const left = Math.min(Math.max(margin, rect.left + rect.width / 2 - SIZE / 2), window.innerWidth - SIZE - margin);
  return (
    <div
      className="fixed z-[100] pointer-events-none flex items-center justify-center bg-white shadow-2xl border border-[color:var(--border-soft)] p-1.5"
      style={{ top, left, width: SIZE, height: SIZE }}
      data-testid="photo-hover-preview"
    >
      <img src={photoImageUrl(photoId, "medium")} alt="" className="max-w-full max-h-full object-contain" />
    </div>
  );
}
