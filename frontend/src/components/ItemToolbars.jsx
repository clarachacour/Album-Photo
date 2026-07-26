import React, { useRef } from "react";
import { Crop, Trash2, Check, ZoomIn, Bold, Palette } from "lucide-react";

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

/** Frame selected (not yet cropping): move/resize via the frame itself, plus crop + delete actions. */
export function PhotoFrameToolbar({ x, y, w, onCrop, onDelete }) {
  return (
    <ToolbarShell x={x} y={y} w={w}>
      <ToolbarButton onClick={onCrop} title="Recadrer la photo" tid="frame-crop-btn">
        <Crop size={14} />
      </ToolbarButton>
      <ToolbarButton onClick={onDelete} title="Supprimer ce cadre" tid="frame-delete-btn" danger>
        <Trash2 size={14} />
      </ToolbarButton>
    </ToolbarShell>
  );
}

/** In crop mode: drag inside the frame to pan, slider to zoom, check to confirm. */
export function PhotoCropToolbar({ x, y, w, scale, onScaleChange, onDone }) {
  return (
    <ToolbarShell x={x} y={y} w={w}>
      <ZoomIn size={14} />
      <input
        type="range"
        min="0.5"
        max="2.5"
        step="0.05"
        value={scale}
        onChange={(e) => onScaleChange(parseFloat(e.target.value))}
        className="w-24 accent-[color:var(--coral)]"
        data-testid="frame-zoom-slider"
      />
      <ToolbarButton onClick={onDone} title="Terminer le recadrage" tid="frame-crop-done">
        <Check size={14} />
      </ToolbarButton>
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