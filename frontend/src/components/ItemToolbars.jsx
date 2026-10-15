import React, { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2, Check, Bold, Palette, ArrowLeftRight, ChevronUp, ChevronDown, Expand, Sun, Loader2, Copy } from "lucide-react";
import { MAX_ZOOM } from "@/lib/photoFit";
import { DegreesInput } from "@/components/DegreesInput";
import { FontPicker } from "@/components/FontPicker";

const TOOLBAR_COLORS = ["#1A1A17", "#F9F8F6", "#E07A5F", "#3D405B", "#81B29A"];

/**
 * How far (CSS px) to slide a toolbar sideways so it stays on screen, from
 * where it is now: its on-screen box, its CSS width and its current shift.
 * On a scaled page (rect.width ≠ offsetWidth) a shift of n CSS px moves it
 * by n × scale on screen — the reason it's worked out in one go here.
 */
export function toolbarShift(rect, offsetWidth, currentShift, windowWidth, margin = 4) {
  const scale = rect.width / offsetWidth || 1;
  const left = rect.left - currentShift * scale;
  const right = rect.right - currentShift * scale;
  let next = 0;
  if (left < margin) next = margin - left;
  else if (right > windowWidth - margin) next = windowWidth - margin - right;
  return next / scale;
}

function ToolbarShell({ x, y, w, children, wide }) {
  // Centred above the item, but slid sideways when that would put part of
  // it off the screen (a photo against the edge of a page, on a phone).
  const ref = useRef(null);
  const [shift, setShift] = useState(0);
  const shiftRef = useRef(0);
  shiftRef.current = shift;
  // Measured once per position, not again after its own shift: on a
  // scaled-up page (pinch zoom, a cover drawn larger) a shift of n px moves
  // the toolbar by more than n on screen, and measuring again after each
  // shift never settled ("Maximum update depth exceeded").
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !el.offsetWidth) return;
    const rect = el.getBoundingClientRect();
    const next = toolbarShift(rect, el.offsetWidth, shiftRef.current, window.innerWidth);
    if (Math.abs(next - shiftRef.current) > 0.5) setShift(next);
  }, [x, y, w, wide]);
  return (
    <div
      ref={ref}
      data-item-toolbar
      className={`absolute z-40 flex items-center gap-1 bg-[color:var(--ink)] text-[color:var(--paper)] px-1.5 py-1 shadow-lg rounded-sm ${wide ? "flex-wrap max-w-[300px]" : ""}`}
      style={{
        left: `${(x + w / 2) * 100}%`,
        top: `${y * 100}%`,
        transform: `translate(calc(-50% + ${shift}px), calc(-100% - 8px))`,
      }}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>
  );
}

// `label`: the button's short name, always shown under its icon (the same
// on a computer, an iPad or a phone — touch screens have no tooltips).
function ToolbarButton({ onClick, title, tid, danger, label, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      data-testid={tid}
      className={`tap-target p-1.5 rounded-sm hover:bg-white/20 transition-colors inline-flex flex-col items-center ${danger ? "text-red-300 hover:text-red-200" : ""}`}
    >
      {children}
      {label && <span className="mt-1 text-[9px] leading-none whitespace-nowrap opacity-90">{label}</span>}
    </button>
  );
}

/** Frame selected (not yet editing): move/resize via the frame itself, plus edit + swap + layer + delete actions. */
export function PhotoFrameToolbar({ x, y, w, onEdit, onSwap, isSwapping, onBringForward, onSendBackward, onDelete, onShowWhole, emptyFrame, hideSwap, hideReorder, brighten, onDuplicate }) {
  const { t } = useTranslation();
  const [brightenOpen, setBrightenOpen] = useState(false);
  return (
    <ToolbarShell x={x} y={y} w={w}>
      {!emptyFrame && (
        <>
          <ToolbarButton onClick={onEdit} title={t("toolbars.editPhoto")} tid="frame-edit-btn" label={t("toolbars.short.edit")}>
            <Pencil size={14} />
          </ToolbarButton>
          {/* A dark photo (or a brightened copy): lighter copies to choose
              from, or back to the original. */}
          {brighten && (
            <div className="relative">
              <ToolbarButton onClick={() => setBrightenOpen((v) => !v)} title={t("toolbars.brighten")} tid="frame-brighten-btn" label={t("toolbars.short.brighten")}>
                {brighten.busy ? <Loader2 size={14} className="animate-spin" /> : <Sun size={14} className={brighten.level ? "text-amber-300" : ""} />}
              </ToolbarButton>
              {brightenOpen && !brighten.busy && (
                <div className="absolute left-1/2 top-full mt-2 -translate-x-1/2 flex flex-col bg-[color:var(--ink)] rounded-sm shadow-lg py-1 min-w-[150px]" data-testid="frame-brighten-menu">
                  {[null, "light", "strong"].map((level) => (
                    <button
                      key={level || "original"}
                      type="button"
                      onClick={() => {
                        setBrightenOpen(false);
                        if (level !== brighten.level) brighten.onPick(level);
                      }}
                      className={`text-left text-xs px-3 py-1.5 hover:bg-white/20 ${level === brighten.level ? "text-amber-300" : ""}`}
                      data-testid={`frame-brighten-${level || "original"}`}
                    >
                      {t(`toolbars.brightenLevels.${level || "original"}`)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {/* Only when the frame hides part of the photo (see isCropped). */}
          {onShowWhole && (
            <ToolbarButton onClick={onShowWhole} title={t("toolbars.showWholePhoto")} tid="frame-show-whole-btn" label={t("toolbars.short.whole")}>
              <Expand size={14} />
            </ToolbarButton>
          )}
          {!hideSwap && (
            <ToolbarButton
              onClick={onSwap}
              title={isSwapping ? t("toolbars.clickToSwap") : t("toolbars.swapWithAnother")}
              tid="frame-swap-btn" label={t("toolbars.short.swap")}
            >
              <ArrowLeftRight size={14} className={isSwapping ? "text-[color:var(--coral)]" : ""} />
            </ToolbarButton>
          )}
        </>
      )}
      {onDuplicate && !emptyFrame && (
        <ToolbarButton onClick={onDuplicate} title={t("toolbars.duplicate")} tid="frame-duplicate-btn" label={t("toolbars.short.duplicate")}>
          <Copy size={14} />
        </ToolbarButton>
      )}
      {!hideReorder && (
        <>
          <ToolbarButton onClick={onSendBackward} title={t("toolbars.sendBackward")} tid="frame-layer-back-btn" label={t("toolbars.short.back")}>
            <ChevronDown size={14} />
          </ToolbarButton>
          <ToolbarButton onClick={onBringForward} title={t("toolbars.bringForward")} tid="frame-layer-front-btn" label={t("toolbars.short.front")}>
            <ChevronUp size={14} />
          </ToolbarButton>
        </>
      )}
      <ToolbarButton onClick={onDelete} title={t("toolbars.deleteFrame")} tid="frame-delete-btn" label={t("toolbars.short.delete")} danger>
        <Trash2 size={14} />
      </ToolbarButton>
    </ToolbarShell>
  );
}

/** Editing the photo ("Modifier"): drag inside the frame to pan; zoom;
 * turn the photo in its frame (slider, exact degrees, or the round handle
 * on the photo); turn the whole frame (slider or exact degrees); check to
 * confirm. Every rotation lives here, nowhere else. */
export function PhotoEditToolbar({ x, y, w, scale, minScale = 1, onScaleChange, rotation, onRotationChange, frameRotation, onFrameRotationChange, onDone }) {
  const { t } = useTranslation();
  const label = "text-[10px] uppercase tracking-wider text-white/70 whitespace-nowrap";
  return (
    <ToolbarShell x={x} y={y} w={w} wide>
      <div className="flex items-start gap-2">
        <div className="grid items-center gap-x-2 gap-y-1.5" style={{ gridTemplateColumns: "auto 84px auto" }}>
          <span className={label}>{t("toolbars.short.zoom")}</span>
          <input
            type="range"
            min={minScale}
            max={MAX_ZOOM}
            step="0.01"
            value={Math.min(MAX_ZOOM, Math.max(minScale, scale))}
            onChange={(e) => onScaleChange(parseFloat(e.target.value))}
            className="w-[84px] accent-[color:var(--coral)]"
            data-testid="frame-zoom-slider"
          />
          <span />
          <span className={label} title={t("toolbars.turnPhoto")}>{t("toolbars.photo")}</span>
          <input
            type="range"
            min="-180"
            max="180"
            step="1"
            value={rotation}
            onChange={(e) => onRotationChange(parseFloat(e.target.value))}
            className="w-[84px] accent-[color:var(--coral)]"
            data-testid="frame-rotation-slider"
            title={t("toolbars.turnPhoto")}
          />
          <DegreesInput value={rotation} onChange={onRotationChange} tid="frame-rotation-input" dark />
          {onFrameRotationChange && (
            <>
              <span className={label} title={t("toolbars.turnFrame")}>{t("toolbars.frame")}</span>
              <input
                type="range"
                min="-180"
                max="180"
                step="1"
                value={frameRotation || 0}
                onChange={(e) => onFrameRotationChange(parseFloat(e.target.value))}
                className="w-[84px] accent-[color:var(--coral)]"
                data-testid="frame-turn-slider"
                title={t("toolbars.turnFrame")}
              />
              <DegreesInput value={frameRotation || 0} onChange={onFrameRotationChange} tid="frame-turn-input" dark />
            </>
          )}
        </div>
        <ToolbarButton onClick={onDone} title={t("toolbars.done")} tid="frame-edit-done" label={t("toolbars.short.done")}>
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
      className="absolute inset-0 cursor-move touch-none"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      data-testid="photo-pan-overlay"
    />
  );
}

/** Text item selected: compact inline controls, no side panel. */
export function TextItemToolbar({ x, y, w, item, onChange, onDelete, onDuplicate }) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = React.useState(false);
  return (
    <ToolbarShell x={x} y={y} w={w} wide>
      <FontPicker
        dark
        preferUp
        tid="text-toolbar-font"
        // What the page shows for a text without a font (AlbumPage).
        value={item.font || "'Cormorant Garamond', serif"}
        onChange={(v) => onChange({ font: v })}
        className="w-[104px] shrink-0"
      />
      <div className="flex items-center gap-1 shrink-0">
        <ToolbarButton
          onClick={() => onChange({ font_size: Math.max(8, (item.font_size || 16) - 2) })}
          title={t("toolbars.decreaseFontSize")}
          tid="text-toolbar-size-down"
        >
          <span className="text-xs w-3 inline-block text-center">−</span>
        </ToolbarButton>
        <span className="text-xs w-6 text-center">{item.font_size || 16}</span>
        <ToolbarButton
          onClick={() => onChange({ font_size: Math.min(96, (item.font_size || 16) + 2) })}
          title={t("toolbars.increaseFontSize")}
          tid="text-toolbar-size-up"
        >
          <span className="text-xs w-3 inline-block text-center">+</span>
        </ToolbarButton>
      </div>
      <ToolbarButton
        onClick={() => onChange({ font_weight: (item.font_weight === "bold" || item.font_weight === "700") ? "normal" : "bold" })}
        title={t("toolbars.bold")}
        tid="text-toolbar-bold" label={t("toolbars.short.bold")}
      >
        <Bold size={13} />
      </ToolbarButton>
      <div className="relative">
        <ToolbarButton onClick={() => setPickerOpen((v) => !v)} title={t("toolbars.textColor")} tid="text-toolbar-color-toggle" label={t("toolbars.short.color")}>
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
                placeholder={t("toolbars.hexPlaceholder")}
                className="flex-1 min-w-0 bg-white/10 text-[color:var(--paper)] text-xs px-1.5 py-1 rounded-sm border border-white/20 font-mono"
                data-testid="text-toolbar-color-hex"
              />
            </div>
          </div>
        )}
      </div>
      {onDuplicate && (
        <ToolbarButton onClick={onDuplicate} title={t("toolbars.duplicate")} tid="text-toolbar-duplicate" label={t("toolbars.short.duplicate")}>
          <Copy size={13} />
        </ToolbarButton>
      )}
      <ToolbarButton onClick={onDelete} title={t("toolbars.deleteText")} tid="text-toolbar-delete" label={t("toolbars.short.delete")} danger>
        <Trash2 size={14} />
      </ToolbarButton>
    </ToolbarShell>
  );
}
