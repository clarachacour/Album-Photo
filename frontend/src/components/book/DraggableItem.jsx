import React, { useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";

/**
 * Common draggable + resizable wrapper for items placed with normalized
 * (0-1, top-left origin) coordinates. Requires containerRef pointing to the
 * page element (so we can compute pointer position relative to it).
 *
 * Props:
 *   item         - {id, x, y, w, h, ...}
 *   onChange     - (patch) => void
 *   onSelect     - () => void
 *   selected     - bool
 *   containerRef - React ref for the page container
 *   editable     - bool
 */
export function DraggableItem({ item, onChange, onSelect, selected, containerRef, editable, children, extraStyle, tid, minW = 0.05, minH = 0.03, onDragStateChange, onDoubleClick }) {
  const { t } = useTranslation();
  const dragState = useRef(null);
  const lastClickAtRef = useRef(0);

  const onPointerDown = useCallback((e) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
    // Manual double-click detection (two pointerdowns within 400ms) — the
    // browser's native dblclick can miss this because the toolbar appears
    // right after the first click and may intercept the second one.
    const now = Date.now();
    if (onDoubleClick && now - lastClickAtRef.current < 400) {
      lastClickAtRef.current = 0;
      onDoubleClick();
      return;
    }
    lastClickAtRef.current = now;
    if (!containerRef?.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragState.current = {
      mode: "move",
      startX: e.clientX,
      startY: e.clientY,
      startItemX: item.x,
      startItemY: item.y,
      rectW: rect.width,
      rectH: rect.height,
    };
    onDragStateChange && onDragStateChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.x, item.y, onSelect, containerRef, onDragStateChange, onDoubleClick]);

  const onResizePointerDown = useCallback((e) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
    if (!containerRef?.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragState.current = {
      mode: "resize",
      startX: e.clientX,
      startY: e.clientY,
      startItemW: item.w,
      startItemH: item.h,
      rectW: rect.width,
      rectH: rect.height,
    };
    onDragStateChange && onDragStateChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.w, item.h, onSelect, containerRef, onDragStateChange]);

  const onPointerMove = useCallback((e) => {
    if (!dragState.current) return;
    const ds = dragState.current;
    const dx = (e.clientX - ds.startX) / ds.rectW;
    const dy = (e.clientY - ds.startY) / ds.rectH;
    if (ds.mode === "move") {
      const nx = Math.max(0, Math.min(1 - item.w, ds.startItemX + dx));
      const ny = Math.max(0, Math.min(1 - item.h, ds.startItemY + dy));
      onChange({ x: nx, y: ny });
    } else if (ds.mode === "resize") {
      const nw = Math.max(minW, Math.min(1 - item.x, ds.startItemW + dx));
      const nh = Math.max(minH, Math.min(1 - item.y, ds.startItemH + dy));
      onChange({ w: nw, h: nh });
    }
  }, [item.w, item.h, item.x, item.y, onChange, minW, minH]);

  const onPointerUp = useCallback((e) => {
    if (dragState.current) {
      const mode = dragState.current.mode;
      dragState.current = null;
      onDragStateChange && onDragStateChange(false, mode);
      try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    }
  }, [onDragStateChange]);

  const style = {
    left: `${item.x * 100}%`,
    top: `${item.y * 100}%`,
    width: `${item.w * 100}%`,
    height: `${item.h * 100}%`,
    ...extraStyle,
  };
  const ring = editable && selected ? "outline outline-2 outline-[color:var(--coral)]" : "";
  return (
    <div
      className={`absolute ${ring} ${editable ? "cursor-move" : ""}`}
      style={style}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={onDoubleClick}
      data-testid={tid}
    >
      {children}
      {editable && selected && (
        <div
          className="absolute -bottom-1.5 -right-1.5 w-4 h-4 bg-[color:var(--coral)] cursor-nwse-resize z-10 rounded-sm"
          onPointerDown={onResizePointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          data-testid={`${tid}-resize`}
          title={t("albumPage.resize")}
        />
      )}
    </div>
  );
}
