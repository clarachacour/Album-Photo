import React, { useRef } from "react";
import { useTranslation } from "react-i18next";
import { defaultItemBox, defaultSpineBox, defaultTitleBox } from "@/lib/coverDefaults";
import { coverItemImageSrc } from "@/lib/api";
import { DEFAULT_COVER } from "@/lib/coverTemplates";
import { deletePatch } from "@/lib/coverEditing";
import { DegreesInput } from "@/components/DegreesInput";
import {
  Bold,
  Type,
  Image as ImageIcon,
  Trash2,
  X as XIcon,
  RotateCcw,
  Undo2,
} from "lucide-react";

// Shared everywhere a Bold toggle appears (title, spine, extra items) —
// used to have three slightly different value sets/detection rules in
// three different places, so a text that looked bold in one context could
// read as "not bold" to the toggle in another.
function isBoldWeight(w) {
  return w === "bold" || Number(w) >= 600;
}

// Which cover field a given spine selection mode edits, and the label to
// show for it — used both by the spine section itself and by the unified
// color field above it, so the two never drift out of sync on which zone
// maps to which field prefix.
function spineZoneInfo(mode) {
  switch (mode) {
    case "spine-title":
      return { prefix: "spine_title", labelKey: "spineTitle", testid: "spine-title" };
    case "spine-subtitle":
      return { prefix: "spine_subtitle", labelKey: "spineSubtitle", testid: "spine-subtitle" };
    case "spine-caption":
      return { prefix: "spine_caption", labelKey: "spineText", testid: "spine-caption" };
    default:
      return null;
  }
}

/**
 * Shared cover-editing side panel — used both by the album creation wizard
 * (CreateAlbum.jsx) and the post-creation book editor (AlbumEditor.jsx).
 */
export function CoverEditorPanel({
  album,
  coverSel,
  updateCover,
  updateCoverItem,
  addCoverText,
  addCoverImage,
  removeCoverItem,
  updateAlbumTitle,
  addSpineText,
  onDismiss,
}) {
  const { t } = useTranslation();
  const cover = album.cover || {};
  const side = coverSel.side || "front";
  const extras = side === "back" ? cover.back_extra_items || [] : cover.extra_items || [];
  const selectedItem =
    coverSel.mode === "item" ? extras.find((it) => it.id === coverSel.itemId) : null;
  const spineZone = spineZoneInfo(coverSel.mode);
  const onSpine = coverSel.mode?.startsWith("spine-");
  // The selected built-in piece (title, spine texts, logo, divider) is
  // deleted the same way as by the Delete key.
  const deleteSelected = () => {
    const patch = deletePatch(coverSel.mode);
    if (!patch) return;
    updateCover(patch);
    onDismiss();
  };

  const addImageInput = useRef(null);
  const replaceImageInput = useRef(null);

  const zoneLabel = side === "back" ? t("coverPanel.back") : t("coverPanel.front");

  // A single "Text color" field that always edits whatever's currently
  // selected — the title, a spine zone, or a selected text item — instead
  // of a title-only field plus a separate spine-zone field plus a third,
  // unlabeled color swatch for items, all three of which only ever
  // affected one specific kind of selection despite looking identical.
  // With nothing text-like selected, it falls back to the cover-wide
  // default color.
  // Each field shows the color actually on the cover (the template's own
  // when nothing was picked), not an empty "default".
  const baseText = cover.text_color || DEFAULT_COVER.text_color;
  const textColorTarget = (() => {
    if (coverSel.mode === "title") {
      return {
        value: cover.title_color || baseText,
        onChange: (v) => updateCover({ title_color: v || null }),
        onReset: () => updateCover({ title_color: null }),
      };
    }
    if (spineZone) {
      const key = `${spineZone.prefix}_color`;
      return {
        value: cover[key] || baseText,
        onChange: (v) => updateCover({ [key]: v || null }),
        onReset: () => updateCover({ [key]: null }),
      };
    }
    if (coverSel.mode === "item" && selectedItem?.type === "text") {
      return {
        value: selectedItem.color || baseText,
        onChange: (v) => updateCoverItem(selectedItem.id, { color: v || null }, side),
        onReset: () => updateCoverItem(selectedItem.id, { color: null }, side),
      };
    }
    return {
      value: baseText,
      onChange: (v) => updateCover({ text_color: v || null }),
      onReset: () => updateCover({ text_color: null }),
    };
  })();

  const field = "w-full border border-[color:var(--ink)]/20 px-2 py-1.5 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";
  const section = "border-t border-[color:var(--border-soft)] pt-2.5 space-y-2";

  return (
    <div className="space-y-2.5" data-testid="cover-editor-panel">
      {/* Entête du panneau */}
      <div className="flex items-center justify-between">
        <div className="eyebrow text-[color:var(--coral)]">
          {t("coverPanel.header", { zone: onSpine ? t("coverPanel.spine") : zoneLabel })}
        </div>
        <button
          onClick={onDismiss}
          className="text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
          data-testid="cover-editor-dismiss"
          aria-label={t("coverPanel.close")}
        >
          <XIcon size={14} />
        </button>
      </div>

      {/* 1. COULEURS (fond + texte, côte à côte) */}
      <div className="grid grid-cols-2 gap-2">
        <ColorField
          label={t("coverPanel.bgColorShort")}
          value={cover.bg_color || DEFAULT_COVER.bg_color}
          onChange={(v) => updateCover({ bg_color: v || null })}
          tid="cover-bg-color"
          onReset={() => updateCover({ bg_color: null })}
        />
        <ColorField
          label={t("coverPanel.textColorShort")}
          value={textColorTarget.value}
          onChange={textColorTarget.onChange}
          tid="cover-text-color"
          onReset={textColorTarget.onReset}
        />
      </div>

      {/* 2. TITRE PRINCIPAL */}
      {coverSel.mode === "title" && (
        <div className={section}>
          <SmallLabel>{t("coverPanel.mainTitle")}</SmallLabel>
          <input
            type="text"
            data-testid="cover-title-content"
            value={album.title || ""}
            onChange={(e) => updateAlbumTitle && updateAlbumTitle(e.target.value)}
            className={field}
            placeholder={t("coverPanel.titlePlaceholder")}
          />
          <div className="flex items-center gap-2">
            <select
              data-testid="cover-title-font"
              aria-label={t("coverPanel.font")}
              value={cover.title_font || "'Baloo 2', sans-serif"}
              onChange={(e) => updateCover({ title_font: e.target.value })}
              className={`${field} flex-1 min-w-0`}
            >
              <FontOptions />
            </select>
            <BoldToggle
              tid="cover-title-bold"
              weight={cover.title_font_weight}
              onToggle={(next) => updateCover({ title_font_weight: next })}
            />
          </div>
          <SliderRow label={t("coverPanel.size")}>
            {cover.title_writing_mode ? (
              <input
                type="range"
                min={20}
                max={120}
                value={cover.title_font_size || 48}
                onChange={(e) => updateCover({ title_font_size: Number(e.target.value) })}
                className="flex-1 min-w-0"
                data-testid="cover-title-size"
              />
            ) : (
              // Horizontal titles always auto-fit to fill the width of
              // their box, so title_font_size itself has no visible effect
              // (it cancels out of that fill calculation). This scale
              // multiplier is what actually grows/shrinks the result.
              <input
                type="range"
                min={0.5}
                max={1.6}
                step={0.02}
                value={cover.title_scale ?? 1}
                onChange={(e) => updateCover({ title_scale: Number(e.target.value) })}
                className="flex-1 min-w-0"
                data-testid="cover-title-size"
              />
            )}
          </SliderRow>
          <SliderRow label={t("coverPanel.rotation")}>
            <input
              type="range"
              min={-180}
              max={180}
              step={1}
              value={cover.title_rotation || 0}
              onChange={(e) => updateCover({ title_rotation: Number(e.target.value) })}
              className="flex-1 min-w-0"
              data-testid="cover-title-rotation"
            />
            <DegreesInput
              value={cover.title_rotation || 0}
              onChange={(deg) => updateCover({ title_rotation: deg })}
              tid="cover-title-rotation-input"
            />
          </SliderRow>
          <div className="grid grid-cols-2 gap-2">
            <ResetPositionButton
              onClick={() =>
                updateCover({
                  ...(({ x, y, w, h }) => ({ title_x: x, title_y: y, title_w: w, title_h: h }))(defaultTitleBox(album)),
                  title_rotation: 0,
                })
              }
            />
            <DeleteButton onClick={deleteSelected} tid="cover-delete-selected" />
          </div>
        </div>
      )}

      {/* 3. TRANCHE (SPINE TITLE / SUBTITLE / CAPTION) */}
      {spineZone && (() => {
        const { prefix, labelKey, testid: testidPrefix } = spineZone;
        const zone = coverSel.mode;
        return (
        <div className={section}>
          <SmallLabel>{t(`coverPanel.${labelKey}`)}</SmallLabel>

          {zone === "spine-caption" && (
            <textarea
              data-testid="spine-caption-content"
              aria-label={t("coverPanel.captionLabel")}
              value={cover.spine_caption || ""}
              onChange={(e) => updateCover({ spine_caption: e.target.value })}
              rows={2}
              className={field}
              placeholder={"CAMILLE & THOMAS\n15 MAY 2025"}
            />
          )}

          {zone === "spine-title" && (
            <div>
              {cover.spine_title_text != null && (
                <div className="flex justify-end mb-1">
                  <button
                    type="button"
                    onClick={() => updateCover({ spine_title_text: null })}
                    className="underline text-[10px] text-[color:var(--muted)] hover:text-[color:var(--ink)]"
                    data-testid="spine-title-text-reset"
                  >
                    {t("coverPanel.matchCoverTitle")}
                  </button>
                </div>
              )}
              <input
                type="text"
                data-testid="spine-title-text-content"
                value={cover.spine_title_text ?? album?.title ?? ""}
                onChange={(e) => updateCover({ spine_title_text: e.target.value })}
                className={field}
                placeholder={t("coverPanel.sameAsCoverTitle")}
              />
            </div>
          )}

          {(zone === "spine-title" || zone === "spine-subtitle") && (
            <input
              type="text"
              data-testid="spine-subtitle-content"
              aria-label={t("coverPanel.subtitle")}
              value={cover.spine_subtitle || ""}
              onChange={(e) => updateCover({ spine_subtitle: e.target.value })}
              className={field}
              placeholder={t("coverPanel.subtitlePlaceholder")}
            />
          )}

          <div className="flex items-center gap-2">
            <select
              data-testid={`${testidPrefix}-font`}
              aria-label={t("coverPanel.font")}
              value={cover[`${prefix}_font`] || "'Manrope', sans-serif"}
              onChange={(e) => updateCover({ [`${prefix}_font`]: e.target.value })}
              className={`${field} flex-1 min-w-0`}
            >
              <FontOptions />
            </select>
            <BoldToggle
              tid={`${testidPrefix}-bold`}
              weight={cover[`${prefix}_weight`]}
              onToggle={(next) => updateCover({ [`${prefix}_weight`]: next })}
            />
          </div>

          {/* This scales the auto-fit result down (never up) rather than
              setting a raw point size: spine text always auto-fits to the
              spine's real width/word length, so a raw size has no lasting
              effect — this is what actually still does something. */}
          <SliderRow label={t("coverPanel.size")}>
            <input
              type="range"
              min={0.4}
              max={1}
              step={0.02}
              value={cover[`${prefix}_scale`] ?? 1}
              onChange={(e) => updateCover({ [`${prefix}_scale`]: Number(e.target.value) })}
              className="flex-1 min-w-0"
              data-testid={`${testidPrefix}-size`}
            />
          </SliderRow>

          <div className="grid grid-cols-2 gap-2">
            <ResetPositionButton onClick={() => updateCover(defaultSpineBox(album, prefix))} />
            <DeleteButton onClick={deleteSelected} tid="cover-delete-selected" />
          </div>
        </div>
        );
      })()}

      {/* Logo / séparateur de la reliure : seulement « Supprimer » */}
      {(coverSel.mode === "spine-logo" || coverSel.mode === "spine-divider") && (
        <div className={section}>
          <DeleteButton onClick={deleteSelected} tid="cover-delete-selected" />
        </div>
      )}

      {/* 4. ÉLÉMENT AJOUTÉ (texte / forme / image) */}
      {selectedItem && (
        <div className={section}>
          <SmallLabel>{t("coverPanel.selectedItem")}</SmallLabel>

          {selectedItem.type === "text" && (
            <>
              <textarea
                data-testid="cover-item-content"
                value={selectedItem.content || selectedItem.text || ""}
                onChange={(e) =>
                  updateCoverItem(selectedItem.id, { content: e.target.value, text: e.target.value }, side)
                }
                rows={2}
                className={field}
              />
              <div className="flex items-center gap-2">
                <select
                  data-testid="cover-item-font"
                  aria-label={t("coverPanel.font")}
                  value={selectedItem.font || "'Manrope', sans-serif"}
                  onChange={(e) => updateCoverItem(selectedItem.id, { font: e.target.value }, side)}
                  className={`${field} flex-1 min-w-0`}
                >
                  <FontOptions />
                </select>
                <BoldToggle
                  tid="cover-item-bold"
                  weight={selectedItem.font_weight}
                  onToggle={(next) => updateCoverItem(selectedItem.id, { font_weight: next }, side)}
                />
              </div>
              <SliderRow label={t("coverPanel.size")}>
                {selectedItem.role === "subtitle" ? (
                  // Subtitle-role items auto-fit to the title's own size
                  // (see AlbumPage.jsx) — font_size is ignored by that
                  // calculation, so this scales it down instead, same
                  // pattern as the title/spine scale sliders.
                  <input
                    type="range"
                    min={0.4}
                    max={1}
                    step={0.02}
                    value={selectedItem.font_scale ?? 1}
                    onChange={(e) => updateCoverItem(selectedItem.id, { font_scale: Number(e.target.value) }, side)}
                    className="flex-1 min-w-0"
                    data-testid="cover-item-size"
                  />
                ) : (
                  <>
                    <input
                      type="range"
                      min={10}
                      max={72}
                      value={selectedItem.font_size || selectedItem.fontSize || 22}
                      onChange={(e) =>
                        updateCoverItem(
                          selectedItem.id,
                          { font_size: Number(e.target.value), fontSize: Number(e.target.value) },
                          side
                        )
                      }
                      className="flex-1 min-w-0"
                      data-testid="cover-item-size"
                    />
                    <span className="text-xs w-9 text-right font-mono">
                      {selectedItem.font_size || selectedItem.fontSize || 22}px
                    </span>
                  </>
                )}
              </SliderRow>
            </>
          )}

          {selectedItem.type === "shape" && (
            <input
              type="color"
              data-testid="cover-item-fill"
              value={selectedItem.fill_color || "#E56B55"}
              onChange={(e) => updateCoverItem(selectedItem.id, { fill_color: e.target.value }, side)}
              className="w-full h-8 border border-[color:var(--ink)]/20 cursor-pointer p-0"
            />
          )}

          {selectedItem.type === "image" && (
            <div className="flex items-center gap-2">
              <img
                src={coverItemImageSrc(selectedItem, "medium")}
                alt=""
                className="w-14 h-14 object-contain border border-[color:var(--border-soft)] bg-[color:var(--paper)]"
              />
              <button
                data-testid="cover-item-replace-image"
                onClick={() => replaceImageInput.current?.click()}
                className="flex-1 inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-1.5 hover:border-[color:var(--ink)] transition-colors"
              >
                <ImageIcon size={14} />
                <span className="text-xs font-semibold tracking-wider uppercase">{t("coverPanel.replaceImage")}</span>
              </button>
              <input
                ref={replaceImageInput}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) addCoverImage(f, selectedItem.id, side);
                  e.target.value = "";
                }}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <ResetPositionButton
              onClick={() => updateCoverItem(selectedItem.id, defaultItemBox(album, selectedItem, side), side)}
            />
            <DeleteButton onClick={() => removeCoverItem(selectedItem.id, side)} tid="cover-item-remove" />
          </div>
        </div>
      )}

      {/* 5. AJOUTER (et remettre ce qui a été supprimé) */}
      <div className={section}>
        <SmallLabel>{t("coverPanel.add")}</SmallLabel>
        <div className="grid grid-cols-3 gap-1.5">
          {!onSpine && (
            <>
              <AddButton icon={<Type size={14} />} label={t("coverPanel.text")} onClick={() => addCoverText(undefined, side)} tid="cover-add-text" />
              <AddButton icon={<ImageIcon size={14} />} label={t("coverPanel.image")} onClick={() => addImageInput.current?.click()} tid="cover-add-image" />
            </>
          )}
          {addSpineText && (
            <AddButton
              icon={<Type size={14} />}
              label={t("coverPanel.textOnSpineShort")}
              title={cover.spine_caption && cover.spine_subtitle ? t("coverPanel.spineFull") : t("coverPanel.textOnSpine")}
              onClick={() => addSpineText(cover)}
              disabled={!!cover.spine_caption && !!cover.spine_subtitle}
              tid="spine-add-text"
            />
          )}
        </div>
        {!onSpine && (
          <input
            ref={addImageInput}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) addCoverImage(f, null, side);
              e.target.value = "";
            }}
          />
        )}
        {!onSpine && side === "front" && cover.title_hidden && (
          <RestoreButton label={t("coverPanel.restoreTitle")} onClick={() => updateCover({ title_hidden: false })} tid="cover-restore-title" />
        )}
        {addSpineText && cover.spine_title_hidden && (
          <RestoreButton label={t("coverPanel.restoreSpineTitle")} onClick={() => updateCover({ spine_title_hidden: false })} tid="spine-restore-title" />
        )}
        {addSpineText && cover.spine_logo_image && cover.spine_logo_hidden && (
          <RestoreButton label={t("coverPanel.restoreLogo")} onClick={() => updateCover({ spine_logo_hidden: false })} tid="spine-restore-logo" />
        )}
        {addSpineText && cover.spine_title_caption_divider && cover.spine_divider_hidden && (
          <RestoreButton label={t("coverPanel.restoreDivider")} onClick={() => updateCover({ spine_divider_hidden: false })} tid="spine-restore-divider" />
        )}
      </div>
    </div>
  );
}

function SmallLabel({ children }) {
  return <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--muted)]">{children}</div>;
}

// A slider with its label on the left, on one line.
function SliderRow({ label, children }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--muted)]">{label}</span>
      {children}
    </div>
  );
}

function AddButton({ icon, label, onClick, disabled, title, tid }) {
  return (
    <button
      type="button"
      data-testid={tid}
      onClick={onClick}
      disabled={disabled}
      title={title || label}
      className="inline-flex flex-col items-center justify-center gap-1 border border-[color:var(--ink)]/30 py-1.5 hover:border-[color:var(--ink)] transition-colors disabled:opacity-40 disabled:hover:border-[color:var(--ink)]/30"
    >
      {icon}
      <span className="text-[10px] font-semibold tracking-wider uppercase">{label}</span>
    </button>
  );
}

// Same Bold control everywhere it appears — one set of toggle values
// (700/400) and one detection rule (isBoldWeight), instead of the title,
// spine, and item versions each having their own slightly different
// logic that could disagree about whether the same weight counted as bold.
function BoldToggle({ tid, weight, onToggle }) {
  const { t } = useTranslation();
  const bold = isBoldWeight(weight);
  return (
    <button
      data-testid={tid}
      onClick={() => onToggle(bold ? "400" : "700")}
      className={`shrink-0 inline-flex items-center justify-center w-8 h-8 border transition-colors ${
        bold
          ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
          : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
      }`}
      title={t("coverPanel.bold")}
    >
      <Bold size={14} />
    </button>
  );
}

function DeleteButton({ onClick, tid }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full inline-flex items-center justify-center gap-1.5 border border-red-300 text-red-600 py-1.5 hover:bg-red-50 transition-colors"
      data-testid={tid}
    >
      <Trash2 size={13} />
      <span className="text-[11px] font-semibold tracking-wider uppercase">{t("coverPanel.delete")}</span>
    </button>
  );
}

// Puts back a piece deleted earlier (title, spine title, logo, divider).
function RestoreButton({ label, onClick, tid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={tid}
      className="w-full inline-flex items-center justify-center gap-1.5 border border-[color:var(--ink)]/30 py-1.5 hover:border-[color:var(--ink)] transition-colors"
    >
      <Undo2 size={13} />
      <span className="text-[11px] font-semibold tracking-wider uppercase">{label}</span>
    </button>
  );
}

function ResetPositionButton({ onClick }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full inline-flex items-center justify-center gap-1.5 py-1.5 border border-[color:var(--ink)]/30 text-[11px] font-semibold tracking-wider uppercase hover:border-[color:var(--ink)] transition-colors"
      title={t("coverPanel.resetPosition")}
    >
      <RotateCcw size={12} />
      {t("coverPanel.resetPosition")}
    </button>
  );
}

export function ColorField({ label, value, onChange, tid, onReset }) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between mb-1">
        <SmallLabel>{label}</SmallLabel>
        <button
          type="button"
          onClick={onReset}
          title={t("coverPanel.default")}
          aria-label={t("coverPanel.default")}
          className="text-[color:var(--muted)] hover:text-[color:var(--ink)]"
        >
          <RotateCcw size={10} className="inline -mt-px" /> <span className="text-[10px]">{t("coverPanel.default")}</span>
        </button>
      </div>
      <div className="flex items-center gap-1.5">
        <input
          data-testid={tid}
          type="color"
          value={value || "#FFFFFF"}
          onChange={(e) => onChange(e.target.value)}
          className="w-8 h-8 shrink-0 border border-[color:var(--ink)]/20 cursor-pointer p-0"
        />
        <input
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t("coverPanel.default")}
          className="w-full min-w-0 border border-[color:var(--ink)]/20 px-1.5 py-1.5 text-xs font-mono focus:border-[color:var(--ink)] focus:outline-none"
        />
      </div>
    </div>
  );
}

// The fonts offered for every text on the cover.
const FONTS = [
  ["'Baloo 2', sans-serif", "Baloo", "rounded"],
  ["'Manrope', sans-serif", "Manrope", "sans"],
  ["'Cormorant Garamond', serif", "Cormorant", "serif"],
  ["'Alex Brush', cursive", "Alex Brush", "script"],
  ["Georgia, serif", "Georgia"],
  ["Helvetica, Arial, sans-serif", "Helvetica"],
  ["'Courier New', monospace", "Courier"],
];

function FontOptions() {
  const { t } = useTranslation();
  return FONTS.map(([value, name, kind]) => (
    <option key={value} value={value}>
      {kind ? `${name} (${t(`coverPanel.fonts.${kind}`)})` : name}
    </option>
  ));
}
