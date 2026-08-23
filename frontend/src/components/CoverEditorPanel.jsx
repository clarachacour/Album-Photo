import React, { useRef } from "react";
import {
  Bold,
  Type,
  Image as ImageIcon,
  Trash2,
  X as XIcon,
  EyeOff,
  Eye,
  RotateCcw,
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
      return { prefix: "spine_title", label: "Spine title", testid: "spine-title" };
    case "spine-subtitle":
      return { prefix: "spine_subtitle", label: "Spine subtitle", testid: "spine-subtitle" };
    case "spine-year":
      return { prefix: "spine_year", label: "Spine year", testid: "spine-year" };
    case "spine-caption":
      return { prefix: "spine_caption", label: "Spine text", testid: "spine-caption" };
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
  updateAlbumYear,
  onDismiss,
}) {
  const cover = album.cover || {};
  const side = coverSel.side || "front";
  const extras = side === "back" ? cover.back_extra_items || [] : cover.extra_items || [];
  const selectedItem =
    coverSel.mode === "item" ? extras.find((it) => it.id === coverSel.itemId) : null;
  const spineZone = spineZoneInfo(coverSel.mode);

  const addImageInput = useRef(null);
  const replaceImageInput = useRef(null);

  const zoneLabel = side === "back" ? "Back Cover" : "Front Cover";

  // A single "Text color" field that always edits whatever's currently
  // selected — the title, a spine zone, or a selected text item — instead
  // of a title-only field plus a separate spine-zone field plus a third,
  // unlabeled color swatch for items, all three of which only ever
  // affected one specific kind of selection despite looking identical.
  // With nothing text-like selected, it falls back to the cover-wide
  // default color.
  const textColorTarget = (() => {
    if (coverSel.mode === "title") {
      return {
        value: cover.title_color || "",
        onChange: (v) => updateCover({ title_color: v || null }),
        onReset: () => updateCover({ title_color: null }),
      };
    }
    if (spineZone) {
      const key = `${spineZone.prefix}_color`;
      return {
        value: cover[key] || "",
        onChange: (v) => updateCover({ [key]: v || null }),
        onReset: () => updateCover({ [key]: null }),
      };
    }
    if (coverSel.mode === "item" && selectedItem?.type === "text") {
      return {
        value: selectedItem.color || "",
        onChange: (v) => updateCoverItem(selectedItem.id, { color: v || null }, side),
        onReset: () => updateCoverItem(selectedItem.id, { color: null }, side),
      };
    }
    return {
      value: cover.text_color || "",
      onChange: (v) => updateCover({ text_color: v || null }),
      onReset: () => updateCover({ text_color: null }),
    };
  })();

  return (
    <div className="space-y-3">
      {/* Entête du panneau */}
      <div className="flex items-center justify-between">
        <div className="eyebrow text-[color:var(--coral)]">
          {spineZone ? "Cover — Spine" : `Cover — ${zoneLabel}`}
        </div>
        <button
          onClick={onDismiss}
          className="text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
          data-testid="cover-editor-dismiss"
          aria-label="Fermer"
        >
          <XIcon size={14} />
        </button>
      </div>

      {/* 1. COULEURS DE LA COUVERTURE */}
      <div className="space-y-3">
        <ColorField
          label="Background color"
          value={cover.bg_color || ""}
          onChange={(v) => updateCover({ bg_color: v || null })}
          tid="cover-bg-color"
          onReset={() => updateCover({ bg_color: null })}
        />
        <ColorField
          label="Text color"
          value={textColorTarget.value}
          onChange={textColorTarget.onChange}
          tid="cover-text-color"
          onReset={textColorTarget.onReset}
        />
      </div>

      {/* 2. ÉDITION DU TITRE PRINCIPAL */}
      {coverSel.mode === "title" && (
        <div className="border-t border-[color:var(--border-soft)] pt-3 space-y-2">
          <div className="eyebrow">Main Title</div>
          <textarea
            data-testid="cover-title-content"
            value={album.title || ""}
            onChange={(e) => updateAlbumTitle && updateAlbumTitle(e.target.value)}
            rows={2}
            className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none"
            placeholder="Title of the album"
          />

          <div>
            <label className="eyebrow block mb-2">Font</label>
            <select
              data-testid="cover-title-font"
              value={cover.title_font || "'Baloo 2', sans-serif"}
              onChange={(e) => updateCover({ title_font: e.target.value })}
              className="w-full border border-[color:var(--ink)]/20 p-2 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none"
            >
              <option value="'Baloo 2', sans-serif">Baloo (rounded)</option>
              <option value="'Cormorant Garamond', serif">Cormorant (serif)</option>
              <option value="'Alex Brush', cursive">Alex Brush (script)</option>
              <option value="'Manrope', sans-serif">Manrope (sans)</option>
              <option value="Georgia, serif">Georgia</option>
              <option value="Helvetica, Arial, sans-serif">Helvetica</option>
              <option value="'Courier New', monospace">Courier</option>
            </select>
          </div>

          <div>
            <label className="eyebrow block mb-2">Title Size</label>
            {cover.title_writing_mode ? (
              <input
                type="range"
                min={20}
                max={120}
                value={cover.title_font_size || 48}
                onChange={(e) => updateCover({ title_font_size: Number(e.target.value) })}
                className="w-full"
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
                className="w-full"
                data-testid="cover-title-size"
              />
            )}
          </div>

          <div className="flex items-center gap-2">
            <BoldToggle
              tid="cover-title-bold"
              weight={cover.title_font_weight}
              onToggle={(next) => updateCover({ title_font_weight: next })}
            />
            <ResetPositionButton
              onClick={() =>
                updateCover({
                  title_x: 0.05,
                  title_y: 0.05,
                  title_w: 0.9,
                  title_h: 0.2,
                })
              }
            />
          </div>
        </div>
      )}

      {/* 3. ÉDITION DE LA TRANCHE (SPINE TITLE / SUBTITLE / YEAR / CAPTION) */}
      {spineZone && (() => {
        const { prefix, label, testid: testidPrefix } = spineZone;
        const zone = coverSel.mode;
        return (
        <div className="border-t border-[color:var(--border-soft)] pt-3 space-y-2">
          <div className="eyebrow">{label}</div>

          {zone === "spine-year" && updateAlbumYear && (
            <div>
              <label className="eyebrow block mb-2">Year</label>
              <input
                type="text"
                value={album.year || new Date().getFullYear()}
                onChange={(e) => updateAlbumYear(e.target.value)}
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none"
              />
            </div>
          )}

          {zone === "spine-caption" && (
            <div>
              <label className="eyebrow block mb-2">Text (2 lines)</label>
              <textarea
                data-testid="spine-caption-content"
                value={cover.spine_caption || ""}
                onChange={(e) => updateCover({ spine_caption: e.target.value })}
                rows={2}
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none"
                placeholder={"CAMILLE & THOMAS\n15 MAY 2025"}
              />
            </div>
          )}

          {zone === "spine-title" && (
            <div>
              <label className="eyebrow flex items-center justify-between mb-2">
                <span>Spine Title</span>
                {cover.spine_title_text != null && (
                  <button
                    type="button"
                    onClick={() => updateCover({ spine_title_text: null })}
                    className="underline text-[10px] normal-case tracking-normal font-normal"
                    data-testid="spine-title-text-reset"
                  >
                    match cover title
                  </button>
                )}
              </label>
              <input
                type="text"
                data-testid="spine-title-text-content"
                value={cover.spine_title_text ?? album?.title ?? ""}
                onChange={(e) => updateCover({ spine_title_text: e.target.value })}
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none"
                placeholder="Same as the cover title"
              />
            </div>
          )}

          {(zone === "spine-title" || zone === "spine-subtitle") && (
            <div>
              <label className="eyebrow block mb-2">Subtitle</label>
              <input
                type="text"
                data-testid="spine-subtitle-content"
                value={cover.spine_subtitle || ""}
                onChange={(e) => updateCover({ spine_subtitle: e.target.value })}
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none"
                placeholder="Optional — shown right after the title"
              />
            </div>
          )}

          <div>
            <label className="eyebrow block mb-2">Font</label>
            <select
              data-testid={`${testidPrefix}-font`}
              value={cover[`${prefix}_font`] || "'Manrope', sans-serif"}
              onChange={(e) => updateCover({ [`${prefix}_font`]: e.target.value })}
              className="w-full border border-[color:var(--ink)]/20 p-2 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none"
            >
              <option value="'Baloo 2', sans-serif">Baloo (rounded)</option>
              <option value="'Manrope', sans-serif">Manrope (sans)</option>
              <option value="'Cormorant Garamond', serif">Cormorant (serif)</option>
              <option value="'Alex Brush', cursive">Alex Brush (script)</option>
              <option value="Georgia, serif">Georgia</option>
              <option value="Helvetica, Arial, sans-serif">Helvetica</option>
              <option value="'Courier New', monospace">Courier</option>
            </select>
          </div>

          <div>
            <label className="eyebrow block mb-2">Size</label>
            {/* This scales the auto-fit result down (never up) rather
                than setting a raw point size. Spine text always auto-fits
                to the spine's real width/word length now, so a raw size
                no longer has any lasting effect once the page has
                rendered once — this is what actually still does
                something. */}
            <input
              type="range"
              min={0.4}
              max={1}
              step={0.02}
              value={cover[`${prefix}_scale`] ?? 1}
              onChange={(e) => updateCover({ [`${prefix}_scale`]: Number(e.target.value) })}
              className="w-full"
              data-testid={`${testidPrefix}-size`}
            />
          </div>

          <div className="flex items-center gap-2">
            <BoldToggle
              tid={`${testidPrefix}-bold`}
              weight={cover[`${prefix}_weight`]}
              onToggle={(next) => updateCover({ [`${prefix}_weight`]: next })}
            />
            <ResetPositionButton
              onClick={() =>
                updateCover({
                  [`${prefix}_y`]: null,
                  [`${prefix}_h`]: null,
                })
              }
            />
          </div>

          {zone !== "spine-caption" && zone !== "spine-subtitle" && (
            <button
              onClick={() => updateCover({ [`${prefix}_hidden`]: !cover[`${prefix}_hidden`] })}
              className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors"
              data-testid={`${testidPrefix}-toggle`}
            >
              {cover[`${prefix}_hidden`] ? <Eye size={14} /> : <EyeOff size={14} />}
              <span className="text-xs font-semibold tracking-widest uppercase">
                {cover[`${prefix}_hidden`] ? "Show" : "Hide"}
              </span>
            </button>
          )}
          {(zone === "spine-caption" || zone === "spine-subtitle") && (cover.spine_caption || cover.spine_subtitle) && (
            <button
              onClick={() => updateCover(zone === "spine-caption" ? { spine_caption: "" } : { spine_subtitle: "" })}
              className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors"
              data-testid={zone === "spine-caption" ? "spine-caption-clear" : "spine-subtitle-clear"}
            >
              <EyeOff size={14} />
              <span className="text-xs font-semibold tracking-widest uppercase">Clear</span>
            </button>
          )}
        </div>
        );
      })()}

      {/* 4. ÉDITION D'UN ÉLÉMENT SÉLECTIONNÉ (EXTRA ITEM) */}
      {selectedItem && (
        <div className="border-t border-[color:var(--border-soft)] pt-3 space-y-2">
          <div className="eyebrow">Selected Item</div>

          {selectedItem.type === "text" && (
            <>
              <textarea
                data-testid="cover-item-content"
                value={selectedItem.content || selectedItem.text || ""}
                onChange={(e) =>
                  updateCoverItem(
                    selectedItem.id,
                    { content: e.target.value, text: e.target.value },
                    side
                  )
                }
                rows={2}
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none"
              />
              <select
                data-testid="cover-item-font"
                value={selectedItem.font || "'Manrope', sans-serif"}
                onChange={(e) =>
                  updateCoverItem(selectedItem.id, { font: e.target.value }, side)
                }
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none"
              >
                <option value="'Baloo 2', sans-serif">Baloo (rounded)</option>
                <option value="'Manrope', sans-serif">Manrope (sans)</option>
                <option value="'Cormorant Garamond', serif">Cormorant (serif)</option>
                <option value="'Alex Brush', cursive">Alex Brush (script)</option>
                <option value="Georgia, serif">Georgia</option>
                <option value="Helvetica, Arial, sans-serif">Helvetica</option>
                <option value="'Courier New', monospace">Courier</option>
              </select>
              <div className="flex items-center gap-2">
                <BoldToggle
                  tid="cover-item-bold"
                  weight={selectedItem.font_weight}
                  onToggle={(next) => updateCoverItem(selectedItem.id, { font_weight: next }, side)}
                />
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
                    onChange={(e) =>
                      updateCoverItem(selectedItem.id, { font_scale: Number(e.target.value) }, side)
                    }
                    className="flex-1"
                    data-testid="cover-item-size"
                  />
                ) : (
                  <input
                    type="range"
                    min={10}
                    max={72}
                    value={selectedItem.font_size || selectedItem.fontSize || 22}
                    onChange={(e) =>
                      updateCoverItem(
                        selectedItem.id,
                        {
                          font_size: Number(e.target.value),
                          fontSize: Number(e.target.value),
                        },
                        side
                      )
                    }
                    className="flex-1"
                    data-testid="cover-item-size"
                  />
                )}
                {selectedItem.role !== "subtitle" && (
                  <span className="text-xs w-8 text-right font-mono">
                    {selectedItem.font_size || selectedItem.fontSize || 22}px
                  </span>
                )}
              </div>
            </>
          )}

          {selectedItem.type === "shape" && (
            <input
              type="color"
              data-testid="cover-item-fill"
              value={selectedItem.fill_color || "#E56B55"}
              onChange={(e) =>
                updateCoverItem(selectedItem.id, { fill_color: e.target.value }, side)
              }
              className="w-full h-9 border border-[color:var(--ink)]/20 cursor-pointer p-0"
            />
          )}

          {selectedItem.type === "image" && (
            <>
              <img
                src={selectedItem.image_url}
                alt=""
                className="w-full max-h-32 object-contain border border-[color:var(--border-soft)] bg-[color:var(--paper)]"
              />
              <button
                data-testid="cover-item-replace-image"
                onClick={() => replaceImageInput.current?.click()}
                className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors"
              >
                <ImageIcon size={14} />
                <span className="text-xs font-semibold tracking-widest uppercase">
                  Replace image
                </span>
              </button>
              <input
                ref={replaceImageInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) addCoverImage(f, selectedItem.id, side);
                  e.target.value = "";
                }}
              />
            </>
          )}

          <ResetPositionButton
            onClick={() =>
              updateCoverItem(
                selectedItem.id,
                { x: 0.1, y: 0.1, w: 0.5, h: selectedItem.type === "text" ? 0.1 : 0.3 },
                side
              )
            }
          />

          <button
            onClick={() => removeCoverItem(selectedItem.id, side)}
            className="w-full inline-flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2 hover:bg-red-50 transition-colors"
            data-testid="cover-item-remove"
          >
            <Trash2 size={14} />
            <span className="text-xs font-semibold tracking-widest uppercase">
              Delete
            </span>
          </button>
        </div>
      )}

      {/* 5. AJOUT D'ÉLÉMENTS SUR LA COUVERTURE */}
      <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-2">
        <div className="eyebrow">Add — {zoneLabel}</div>
        <button
          data-testid="cover-add-text"
          onClick={() => addCoverText(undefined, side)}
          className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors"
        >
          <Type size={14} />
          <span className="text-xs font-semibold tracking-widest uppercase">Text</span>
        </button>
        <button
          data-testid="cover-add-image"
          onClick={() => addImageInput.current?.click()}
          className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors"
        >
          <ImageIcon size={14} />
          <span className="text-xs font-semibold tracking-widest uppercase">Image</span>
        </button>
        <input
          ref={addImageInput}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) addCoverImage(f, null, side);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}

// Same Bold control everywhere it appears — one set of toggle values
// (700/400) and one detection rule (isBoldWeight), instead of the title,
// spine, and item versions each having their own slightly different
// logic that could disagree about whether the same weight counted as bold.
function BoldToggle({ tid, weight, onToggle }) {
  const bold = isBoldWeight(weight);
  return (
    <button
      data-testid={tid}
      onClick={() => onToggle(bold ? "400" : "700")}
      className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
        bold
          ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
          : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
      }`}
      title="Bold"
    >
      <Bold size={14} />
    </button>
  );
}

function ResetPositionButton({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-3 py-2 border border-[color:var(--ink)]/30 text-xs font-semibold uppercase hover:border-[color:var(--ink)] transition-colors"
      title="Reset position"
    >
      <RotateCcw size={12} />
      Reset position
    </button>
  );
}

export function ColorField({ label, value, onChange, tid, onReset }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="eyebrow">{label}</label>
        <button
          onClick={onReset}
          className="text-[10px] text-[color:var(--muted)] hover:text-[color:var(--ink)] underline"
        >
          default
        </button>
      </div>
      <div className="flex items-center gap-2">
        <input
          data-testid={tid}
          type="color"
          value={value || "#FFFFFF"}
          onChange={(e) => onChange(e.target.value)}
          className="w-9 h-9 border border-[color:var(--ink)]/20 cursor-pointer p-0"
        />
        <input
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="default"
          className="flex-1 border border-[color:var(--ink)]/20 px-2 py-1 text-xs font-mono focus:border-[color:var(--ink)] focus:outline-none"
        />
      </div>
    </div>
  );
}
