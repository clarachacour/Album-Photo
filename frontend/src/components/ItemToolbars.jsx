import React, { useRef } from "react";
import { Pencil, Trash2, Check, ZoomIn, Bold, Palette, RotateCw, ArrowLeftRight, ChevronUp, ChevronDown } from "lucide-react";

const TOOLBAR_FONTS = [
  { label: "Manrope", value: "'Manrope', sans-serif" },
  { label: "Baloo", value: "'Baloo 2', sans-serif" },
  { label: "Cormorant", value: "'Cormorant Garamond', serif" },
  { label: "Georgia", value: "Georgia, serif" },
  { label: "Courier", value: "'Courier New', monospace" },
];

const TOOLBAR_COLORS = ["#1A1A17", "#F9F8F6", "#E07A5F", "#3D405B", "#81B29A"];

function ToolbarShell({ x, y, w, children, wide }) {
  return (
    <div
      className={`absolute z-40 flex items-center gap-1 bg-[color:var(--ink)] text-[color:var(--paper)] px-1.5 py-1 shadow-lg rounded-sm ${wide ? "flex-wrap max-w-[260px]" : ""}`}
      style={{
        left: `${(x + w / 2) * 100}%`,
        top: `${y * 100}%`,
        transform: "translate(-50%, calc(-100% - 8px))",
      }}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>
  );
}

function ToolbarButton({ onClick, title, tid, danger, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      data-testid={tid}
      className={`p-1.5 rounded-sm hover:bg-white/20 transition-colors ${danger ? "text-red-300 hover:text-red-200" : ""}`}
    >
      {children}
    </button>
  );
}

/** Frame selected (not yet editing): move/resize via the frame itself, plus edit + swap + layer + delete actions. */
export function PhotoFrameToolbar({ x, y, w, onEdit, onSwap, isSwapping, onBringForward, onSendBackward, onDelete, emptyFrame, hideSwap, hideReorder }) {
  return (
    <ToolbarShell x={x} y={y} w={w}>
      {!emptyFrame && (
        <>
          <ToolbarButton onClick={onEdit} title="Edit photo" tid="frame-edit-btn">
            <Pencil size={14} />
          </ToolbarButton>
          {!hideSwap && (
            <ToolbarButton
              onClick={onSwap}
              title={isSwapping ? "Click another photo to swap" : "Swap with another photo"}
              tid="frame-swap-btn"
            >
              <ArrowLeftRight size={14} className={isSwapping ? "text-[color:var(--coral)]" : ""} />
            </ToolbarButton>
          )}
        </>
      )}
      {!hideReorder && (
        <>
          <ToolbarButton onClick={onSendBackward} title="Send backward" tid="frame-layer-back-btn">
            <ChevronDown size={14} />
          </ToolbarButton>
          <ToolbarButton onClick={onBringForward} title="Bring forward" tid="frame-layer-front-btn">
            <ChevronUp size={14} />
          </ToolbarButton>
        </>
      )}
      <ToolbarButton onClick={onDelete} title="Supprimer ce cadre" tid="frame-delete-btn" danger>
        <Trash2 size={14} />
      </ToolbarButton>
    </ToolbarShell>
  );
}

/** Editing the photo itself: drag inside the frame to pan, sliders for zoom
 * and free rotation (any angle — no 90° steps), check to confirm. The exact
 * rotation value sits directly under the rotation slider, not centered
 * under the whole row. */
export function PhotoEditToolbar({ x, y, w, scale, onScaleChange, rotation, onRotationChange, onDone }) {
  return (
    <ToolbarShell x={x} y={y} w={w} wide>
      <div className="flex items-start gap-2">
        <div className="grid items-center gap-x-2 gap-y-1.5" style={{ gridTemplateColumns: "14px 80px 14px 80px" }}>
          <ZoomIn size={14} className="shrink-0" />
          <input
            type="range"
            min="1"
            max="2.5"
            step="0.05"
            value={scale}
            onChange={(e) => onScaleChange(parseFloat(e.target.value))}
            className="w-20 accent-[color:var(--coral)]"
            data-testid="frame-zoom-slider"
          />
          <RotateCw size={14} className="shrink-0" />
          <input
            type="range"
            min="-180"
            max="180"
            step="1"
            value={rotation}
            onChange={(e) => onRotationChange(parseFloat(e.target.value))}
            className="w-20 accent-[color:var(--coral)]"
            data-testid="frame-rotation-slider"
          />
          <div />
          <div />
          <div />
          <input
            type="number"
            min="-180"
            max="180"
            step="1"
            value={Math.round(rotation)}
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              if (!Number.isNaN(v)) onRotationChange(Math.max(-180, Math.min(180, v)));
            }}
            className="w-14 justify-self-center text-center text-[10px] bg-white/10 border border-white/20 rounded-sm tabular-nums"
            data-testid="frame-rotation-input"
          />
        </div>
        <ToolbarButton onClick={onDone} title="Terminer" tid="frame-edit-done">
          <Check size={14} />
        </ToolbarButton>
      </div>
    </ToolbarShell>
  );
}

/** Transparent layer over a photo in crop mode — drag pans the image (focal point), doesn't move the frame. */
export function PhotoPanOverlay({ focalX, focalY, onPan }) {
  const dragRef = useRef(null);

  const onPointerDown = (e) => {
    e.stopPropagation();
    dragRef.current = { startX: e.clientX, startY: e.clientY, startFx: focalX, startFy: focalY };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!dragRef.current) return;
    const d = dragRef.current;
    const dx = (e.clientX - d.startX) / 260;
    const dy = (e.clientY - d.startY) / 260;
    const nfx = Math.min(1, Math.max(0, d.startFx - dx));
    const nfy = Math.min(1, Math.max(0, d.startFy - dy));
    onPan(nfx, nfy);
  };
  const onPointerUp = (e) => {
    dragRef.current = null;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
  };

  return (
    <div
      className="absolute inset-0 cursor-move"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      data-testid="photo-pan-overlay"
    />
  );
}

/** Text item selected: compact inline controls, no side panel. */
export function TextItemToolbar({ x, y, w, item, onChange, onDelete }) {
  const [pickerOpen, setPickerOpen] = React.useState(false);
  return (
    <ToolbarShell x={x} y={y} w={w} wide>
      <select
        value={item.font || TOOLBAR_FONTS[0].value}
        onChange={(e) => onChange({ font: e.target.value })}
        className="bg-transparent text-[color:var(--paper)] text-xs border border-white/30 rounded-sm px-1 py-1"
        data-testid="text-toolbar-font"
      >
        {TOOLBAR_FONTS.map((f) => (
          <option key={f.value} value={f.value} className="text-[color:var(--ink)]">
            {f.label}
          </option>
        ))}
      </select>
      <ToolbarButton
        onClick={() => onChange({ font_size: Math.max(8, (item.font_size || 16) - 2) })}
        title="Réduire"
        tid="text-toolbar-size-down"
      >
        <span className="text-xs w-3 inline-block text-center">−</span>
      </ToolbarButton>
      <span className="text-xs w-6 text-center">{item.font_size || 16}</span>
      <ToolbarButton
        onClick={() => onChange({ font_size: Math.min(96, (item.font_size || 16) + 2) })}
        title="Agrandir"
        tid="text-toolbar-size-up"
      >
        <span className="text-xs w-3 inline-block text-center">+</span>
      </ToolbarButton>
      <ToolbarButton
        onClick={() => onChange({ font_weight: (item.font_weight === "bold" || item.font_weight === "700") ? "normal" : "bold" })}
        title="Gras"
        tid="text-toolbar-bold"
      >
        <Bold size={13} />
      </ToolbarButton>
      <div className="relative">
        <ToolbarButton onClick={() => setPickerOpen((v) => !v)} title="Couleur" tid="text-toolbar-color-toggle">
          <Palette size={13} />
        </ToolbarButton>
        {pickerOpen && (
          <div className="absolute top-full left-0 mt-1 flex flex-col gap-1.5 bg-[color:var(--ink)] p-2 rounded-sm shadow-lg w-40">
            <div className="flex items-center gap-1 flex-wrap">
              {TOOLBAR_COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() => { onChange({ color: c }); setPickerOpen(false); }}
                  className="w-5 h-5 rounded-sm border border-white/30"
                  style={{ background: c }}
                  aria-label={c}
                />
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <input
                type="color"
                value={item.color || "#1A1A17"}
                onChange={(e) => onChange({ color: e.target.value })}
                className="w-6 h-6 cursor-pointer bg-transparent border-0 p-0 shrink-0"
                data-testid="text-toolbar-color-input"
              />
              <input
                type="text"
                value={item.color || "#1A1A17"}
                onChange={(e) => onChange({ color: e.target.value })}
                placeholder="#RRGGBB"
                className="flex-1 min-w-0 bg-white/10 text-[color:var(--paper)] text-xs px-1.5 py-1 rounded-sm border border-white/20 font-mono"
                data-testid="text-toolbar-color-hex"
              />
            </div>
          </div>
        )}
      </div>
      <ToolbarButton onClick={onDelete} title="Supprimer ce texte" tid="text-toolbar-delete" danger>
        <Trash2 size={14} />
      </ToolbarButton>
    </ToolbarShell>
  );
}