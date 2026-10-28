import React, { useRef, useCallback, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { RotateCw } from "lucide-react";

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
 *   onRotate     - (degrees) => void: shows a round handle that turns the
 *                  content (rotation = its current angle)
 *   turnedFrame  - the frame itself is turned by `rotation` (cover title):
 *                  resizing then follows its turned sides
 *   rotateHandleInside - the handle sits inside the frame, at its bottom;
 *                  it then also shows while the frame is locked (photo
 *                  being edited: the handle turns the photo in its frame)
 *   doubleClickMouseOnly - onDoubleClick only with a mouse (not a double tap)
 *   onDropOutside - (clientX, clientY) => void: a move released outside the
 *                  page (onto another page). Past the page's edge, a copy
 *                  of the item follows the pointer over the other page
 *                  (see dragGhost) while the item itself is hidden
 *   rotateHandleBelow - the handle goes on the side facing down (photo
 *                  frames: their toolbar is above them)
 *   edgeHandles  - handles on the 4 sides and 4 corners, not just the
 *                  bottom-right corner (photo frames: cropping a side)
 */
export function rotationFromDrag(startRotation, startAngle, angle) {
  let r = startRotation + angle - startAngle;
  r = ((((r + 180) % 360) + 360) % 360) - 180; // back into -180..180
  // Lands exactly on straight / quarter turns when close to one.
  for (const snap of [-180, -90, 0, 90, 180]) {
    if (Math.abs(r - snap) < 4) return snap === -180 ? 180 : snap;
  }
  return Math.round(r);
}

// Resizing a turned frame: the corner handle's movement is read along the
// frame's own (turned) sides, and the opposite corner stays where it is.
export function rotatedResize(ds, dxPx, dyPx, minW, minH) {
  const a = (ds.rotation * Math.PI) / 180;
  const cos = Math.cos(a), sin = Math.sin(a);
  const along = dxPx * cos + dyPx * sin; // along the frame's width
  const across = -dxPx * sin + dyPx * cos; // along its height
  const w = Math.max(minW, Math.min(1, ds.startItemW + along / ds.rectW));
  const h = Math.max(minH, Math.min(1, ds.startItemH + across / ds.rectH));
  const dw = ((w - ds.startItemW) * ds.rectW) / 2;
  const dh = ((h - ds.startItemH) * ds.rectH) / 2;
  // The center moves by half the growth, turned like the frame.
  const cx = (ds.startItemX + ds.startItemW / 2) * ds.rectW + dw * cos - dh * sin;
  const cy = (ds.startItemY + ds.startItemH / 2) * ds.rectH + dw * sin + dh * cos;
  return { x: cx / ds.rectW - w / 2, y: cy / ds.rectH - h / 2, w, h };
}

// Resizing from any of the 8 handles: (hx, hy) says which sides move
// (-1 left/top, 1 right/bottom, 0 that axis stays). The opposite side stays
// where it is, on a turned frame too (the movement is read along its own
// sides). An unturned frame stays on its page.
export function edgeResize(ds, dxPx, dyPx, minW, minH) {
  const a = ((ds.rotation || 0) * Math.PI) / 180;
  const cos = Math.cos(a), sin = Math.sin(a);
  const along = dxPx * cos + dyPx * sin;
  const across = -dxPx * sin + dyPx * cos;
  let w = ds.hx ? Math.max(minW, Math.min(1, ds.startItemW + (ds.hx * along) / ds.rectW)) : ds.startItemW;
  let h = ds.hy ? Math.max(minH, Math.min(1, ds.startItemH + (ds.hy * across) / ds.rectH)) : ds.startItemH;
  if (!ds.rotation) {
    if (ds.hx < 0) w = Math.min(w, ds.startItemX + ds.startItemW);
    if (ds.hx > 0) w = Math.min(w, 1 - ds.startItemX);
    if (ds.hy < 0) h = Math.min(h, ds.startItemY + ds.startItemH);
    if (ds.hy > 0) h = Math.min(h, 1 - ds.startItemY);
  }
  // The center moves by half the growth, towards the side pulled.
  const lx = (ds.hx * (w - ds.startItemW) * ds.rectW) / 2;
  const ly = (ds.hy * (h - ds.startItemH) * ds.rectH) / 2;
  const cx = (ds.startItemX + ds.startItemW / 2) * ds.rectW + lx * cos - ly * sin;
  const cy = (ds.startItemY + ds.startItemH / 2) * ds.rectH + lx * sin + ly * cos;
  return { x: cx / ds.rectW - w / 2, y: cy / ds.rectH - h / 2, w, h };
}

// The 7 handles added by edgeHandles (the bottom-right one is always
// there): where they sit and the cursor they show.
const EDGE_HANDLES = [
  { hx: -1, hy: -1, name: "top-left", cls: "-top-1.5 -left-1.5 w-3.5 h-3.5 cursor-nwse-resize" },
  { hx: 1, hy: -1, name: "top-right", cls: "-top-1.5 -right-1.5 w-3.5 h-3.5 cursor-nesw-resize" },
  { hx: -1, hy: 1, name: "bottom-left", cls: "-bottom-1.5 -left-1.5 w-3.5 h-3.5 cursor-nesw-resize" },
  { hx: 0, hy: -1, name: "top", cls: "-top-1 left-1/2 -translate-x-1/2 w-6 h-2 cursor-ns-resize" },
  { hx: 0, hy: 1, name: "bottom", cls: "-bottom-1 left-1/2 -translate-x-1/2 w-6 h-2 cursor-ns-resize" },
  { hx: -1, hy: 0, name: "left", cls: "-left-1 top-1/2 -translate-y-1/2 w-2 h-6 cursor-ew-resize" },
  { hx: 1, hy: 0, name: "right", cls: "-right-1 top-1/2 -translate-y-1/2 w-2 h-6 cursor-ew-resize" },
];

const HANDLE_SIDE_CLASS = {
  top: "-top-9 left-1/2 -translate-x-1/2",
  bottom: "-bottom-9 left-1/2 -translate-x-1/2",
  left: "-left-9 top-1/2 -translate-y-1/2",
  right: "-right-9 top-1/2 -translate-y-1/2",
};

// Which side of a frame turned by `rotation` degrees points up on screen
// (or down, when `down`).
export function handleSide(rotation, down = false) {
  const a = ((rotation || 0) * Math.PI) / 180;
  const sides = { top: [0, -1], bottom: [0, 1], left: [-1, 0], right: [1, 0] };
  let best = "top";
  let bestY = Infinity;
  for (const [side, [dx, dy]] of Object.entries(sides)) {
    const screenY = (dx * Math.sin(a) + dy * Math.cos(a)) * (down ? -1 : 1);
    if (screenY < bestY - 1e-9) {
      best = side;
      bestY = screenY;
    }
  }
  return best;
}

// A copy of a dragged item that follows the pointer outside its page: a
// page-sized, see-through layer (so the copy keeps its size and its text
// sizes, which are relative to the page's width) moved along with the
// pointer, above everything. Returns { move(dxPx, dyPx), remove() }.
function dragGhost(itemEl, pageEl, startItemX, startItemY) {
  const page = pageEl.getBoundingClientRect();
  const layer = document.createElement("div");
  Object.assign(layer.style, {
    position: "fixed",
    left: `${page.left}px`,
    top: `${page.top}px`,
    width: `${page.width}px`,
    height: `${page.height}px`,
    containerType: "inline-size",
    pointerEvents: "none",
    zIndex: "9999",
  });
  const copy = itemEl.cloneNode(true);
  copy.removeAttribute("data-testid");
  copy.querySelectorAll("[data-testid]").forEach((el) => el.removeAttribute("data-testid"));
  copy.style.left = `${startItemX * 100}%`;
  copy.style.top = `${startItemY * 100}%`;
  copy.style.opacity = "1";
  copy.style.outline = "none";
  // Just the item: no resize/rotate handles on the copy.
  copy.querySelectorAll("[data-handle]").forEach((el) => el.remove());
  layer.appendChild(copy);
  document.body.appendChild(layer);
  // Its toolbar stays hidden meanwhile (index.css: .dragging-across).
  document.body.classList.add("dragging-across");
  return {
    move: (dx, dy) => {
      layer.style.transform = `translate(${dx}px, ${dy}px)`;
    },
    remove: () => {
      layer.remove();
      document.body.classList.remove("dragging-across");
    },
  };
}

export function DraggableItem({ item, onChange, onSelect, selected, containerRef, editable, children, extraStyle, tid, minW = 0.05, minH = 0.03, onDragStateChange, onDoubleClick, rotation = 0, onRotate, turnedFrame = false, rotateHandleInside = false, rotateHandleBelow = false, onDropOutside, doubleClickMouseOnly = false, edgeHandles = false }) {
  const [outside, setOutside] = useState(false);
  const itemRef = useRef(null);
  const ghostRef = useRef(null);
  const dropGhost = () => {
    ghostRef.current?.remove();
    ghostRef.current = null;
  };
  useEffect(() => dropGhost, []);
  const { t } = useTranslation();
  const dragState = useRef(null);
  const lastClickAtRef = useRef(0);
  const lastPointerTypeRef = useRef("mouse");

  const onPointerDown = useCallback((e) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
    // Manual double-click detection (two pointerdowns within 400ms) — the
    // browser's native dblclick can miss this because the toolbar appears
    // right after the first click and may intercept the second one.
    const now = Date.now();
    lastPointerTypeRef.current = e.pointerType;
    // doubleClickMouseOnly: left to the browser's own dblclick (below),
    // which follows the clicks — a swap started here would be cancelled at
    // once by the click that ends this press.
    if (onDoubleClick && !doubleClickMouseOnly && now - lastClickAtRef.current < 400) {
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
  }, [editable, item.x, item.y, onSelect, containerRef, onDragStateChange, onDoubleClick, doubleClickMouseOnly]);

  // hx/hy: the sides that handle moves (see edgeResize); the bottom-right
  // corner keeps its own way (only w/h change, see onPointerMove).
  const onResizePointerDown = useCallback((e, hx = 1, hy = 1) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
    if (!containerRef?.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragState.current = {
      mode: "resize",
      startX: e.clientX,
      startY: e.clientY,
      startItemX: item.x,
      startItemY: item.y,
      startItemW: item.w,
      startItemH: item.h,
      rotation: turnedFrame ? rotation || 0 : 0,
      rectW: rect.width,
      rectH: rect.height,
      hx,
      hy,
    };
    onDragStateChange && onDragStateChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.x, item.y, item.w, item.h, rotation, turnedFrame, onSelect, containerRef, onDragStateChange]);

  const onRotatePointerDown = useCallback((e) => {
    if (!onRotate) return;
    e.stopPropagation();
    const box = e.currentTarget.parentElement.getBoundingClientRect();
    const cx = box.left + box.width / 2;
    const cy = box.top + box.height / 2;
    dragState.current = {
      mode: "rotate",
      cx,
      cy,
      startAngle: (Math.atan2(e.clientY - cy, e.clientX - cx) * 180) / Math.PI,
      startRotation: rotation || 0,
    };
    onDragStateChange && onDragStateChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [onRotate, rotation, onDragStateChange]);

  const onPointerMove = useCallback((e) => {
    if (!dragState.current) return;
    const ds = dragState.current;
    if (ds.mode === "rotate") {
      const angle = (Math.atan2(e.clientY - ds.cy, e.clientX - ds.cx) * 180) / Math.PI;
      onRotate && onRotate(rotationFromDrag(ds.startRotation, ds.startAngle, angle));
      return;
    }
    const dx = (e.clientX - ds.startX) / ds.rectW;
    const dy = (e.clientY - ds.startY) / ds.rectH;
    if (ds.mode === "move") {
      if (onDropOutside) {
        // As soon as the item would leave its page (where it stays
        // pinned), its copy takes over and keeps following the pointer.
        const ux = ds.startItemX + dx;
        const uy = ds.startItemY + dy;
        const out = ux < -0.005 || uy < -0.005 || ux + item.w > 1.005 || uy + item.h > 1.005;
        if (out !== ds.outside) {
          ds.outside = out;
          setOutside(out);
          if (out && !ghostRef.current && itemRef.current && containerRef?.current) {
            ghostRef.current = dragGhost(itemRef.current, containerRef.current, ds.startItemX, ds.startItemY);
          } else if (!out) {
            dropGhost();
          }
        }
        ghostRef.current?.move(e.clientX - ds.startX, e.clientY - ds.startY);
      }
      const nx = Math.max(0, Math.min(1 - item.w, ds.startItemX + dx));
      const ny = Math.max(0, Math.min(1 - item.h, ds.startItemY + dy));
      onChange({ x: nx, y: ny });
    } else if (ds.mode === "resize" && !(ds.hx === 1 && ds.hy === 1)) {
      onChange(edgeResize(ds, e.clientX - ds.startX, e.clientY - ds.startY, minW, minH));
    } else if (ds.mode === "resize" && ds.rotation) {
      onChange(rotatedResize(ds, e.clientX - ds.startX, e.clientY - ds.startY, minW, minH));
    } else if (ds.mode === "resize") {
      const nw = Math.max(minW, Math.min(1 - item.x, ds.startItemW + dx));
      const nh = Math.max(minH, Math.min(1 - item.y, ds.startItemH + dy));
      onChange({ w: nw, h: nh });
    }
  }, [item.w, item.h, item.x, item.y, onChange, minW, minH, onRotate, onDropOutside, containerRef]);

  const onPointerUp = useCallback((e) => {
    if (dragState.current) {
      const { mode, outside: wasOutside } = dragState.current;
      dragState.current = null;
      setOutside(false);
      dropGhost();
      if (mode === "move" && wasOutside && onDropOutside) onDropOutside(e.clientX, e.clientY);
      onDragStateChange && onDragStateChange(false, mode);
      try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    }
  }, [onDragStateChange, onDropOutside]);

  // Inside the frame when asked, or when a "below" handle would fall off
  // the bottom of the page (the frame's toolbar takes the space above).
  const handleInside = rotateHandleInside || (rotateHandleBelow && item.y + item.h > 0.92);
  const style = {
    left: `${item.x * 100}%`,
    top: `${item.y * 100}%`,
    width: `${item.w * 100}%`,
    height: `${item.h * 100}%`,
    // On a touch screen, a selected frame follows the finger instead of the
    // page scrolling (which used to cut the move short). Unselected frames
    // leave the page scrollable: tap to select, then drag.
    ...(editable && selected ? { touchAction: "none" } : {}),
    ...extraStyle,
    // Past the page's edge, its copy (dragGhost) is what shows.
    ...(outside ? { opacity: 0 } : {}),
  };
  const ring = editable && selected ? "outline outline-2 outline-[color:var(--coral)]" : "";
  return (
    <div
      ref={itemRef}
      className={`absolute ${ring} ${editable ? "cursor-move" : ""}`}
      style={style}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={
        // With doubleClickMouseOnly, a double tap on a touch screen (select,
        // then start dragging) does nothing: only a mouse double-click.
        doubleClickMouseOnly ? () => editable && lastPointerTypeRef.current === "mouse" && onDoubleClick && onDoubleClick() : onDoubleClick
      }
      data-testid={tid}
    >
      {children}
      {editable && selected && (
        <div
          // after: a larger invisible area around the small square, easy to catch with a finger
          className="absolute -bottom-1.5 -right-1.5 w-4 h-4 bg-[color:var(--coral)] cursor-nwse-resize z-10 rounded-sm touch-none pointer-events-auto after:content-[''] after:absolute after:-inset-3"
          onPointerDown={onResizePointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          data-testid={`${tid}-resize`}
          data-handle
          title={t("albumPage.resize")}
        />
      )}
      {editable && selected && edgeHandles &&
        EDGE_HANDLES.map((hd) => (
          <div
            key={hd.name}
            className={`absolute ${hd.cls} bg-[color:var(--coral)] z-10 rounded-sm touch-none pointer-events-auto after:content-[''] after:absolute after:-inset-2.5`}
            onPointerDown={(e) => onResizePointerDown(e, hd.hx, hd.hy)}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            data-testid={`${tid}-resize-${hd.name}`}
            data-handle
            title={t("albumPage.crop")}
          />
        ))}
      {selected && onRotate && (editable || rotateHandleInside) && (
        // Round handle on the side of the frame that faces up on screen,
        // whatever its turn (down when the frame touches the top of the
        // page, where it would be cut off).
        <div
          className={`absolute z-10 pointer-events-auto w-6 h-6 rounded-full bg-[color:var(--coral)] text-white flex items-center justify-center cursor-grab touch-none shadow after:content-[''] after:absolute after:-inset-2 ${handleInside ? "bottom-2 left-1/2 -translate-x-1/2" : HANDLE_SIDE_CLASS[handleSide(rotation, rotateHandleBelow || item.y < 0.08)]}`}
          onPointerDown={onRotatePointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          data-testid={`${tid}-rotate`}
          data-handle
          title={t("albumPage.rotate")}
        >
          <RotateCw size={13} />
        </div>
      )}
    </div>
  );
}
