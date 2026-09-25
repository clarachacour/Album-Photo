import React, { useState } from "react";
import { clampZoom, photoRect } from "@/lib/photoFit";

/**
 * A photo inside its frame (the frame is the parent, with overflow hidden).
 *
 * Zoom 1 = the photo just covers the frame; below 1 it zooms out until the
 * whole photo is visible; above 1 it zooms in. Size and position are computed
 * explicitly (rather than with CSS object-fit) so zooming out can reveal the
 * parts object-fit would crop. At zoom ≥ 1 it renders exactly like the former
 * object-fit: cover + scale() version.
 *
 * photoAspect (width / height) comes from the page item when known; otherwise
 * it's read from the image once loaded (albums created before it was stored).
 */
export function FramedPhoto({ src, frameAspect, photoAspect, zoom = 1, focalX = 0.5, focalY = 0.5, rotation = 0, onAspect }) {
  const [loadedAspect, setLoadedAspect] = useState(null);
  const aspect = photoAspect || loadedAspect;

  const onLoad = (e) => {
    const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
    if (w && h) {
      setLoadedAspect(w / h);
      onAspect && onAspect(w / h);
    }
  };

  const common = {
    src,
    alt: "",
    draggable: false,
    onLoad,
    className: "pointer-events-none select-none",
  };

  if (!aspect || !frameAspect) {
    // Proportions not known yet: same rendering as before, until the image
    // has loaded and its real size can be read.
    return (
      <img
        {...common}
        className={`${common.className} w-full h-full`}
        style={{
          objectFit: "cover",
          objectPosition: `${focalX * 100}% ${focalY * 100}%`,
          transform: `scale(${Math.max(zoom || 1, 1)}) rotate(${rotation}deg)`,
          transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
        }}
      />
    );
  }

  const r = photoRect(frameAspect, aspect, clampZoom(zoom, frameAspect, aspect), focalX, focalY);
  return (
    <img
      {...common}
      style={{
        position: "absolute",
        left: `${r.left * 100}%`,
        top: `${r.top * 100}%`,
        width: `${r.w * 100}%`,
        height: `${r.h * 100}%`,
        maxWidth: "none",
        transform: rotation ? `rotate(${rotation}deg)` : undefined,
        transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
      }}
    />
  );
}
