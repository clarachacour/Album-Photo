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

  const addImageInput = useRef(null);
  const replaceImageInput = useRef(null);

  const zoneLabel = side === "back" ? "Back Cover" : "Front Cover";

  return (
    <div className="space-y-5">
      {/* Entête du panneau */}
      <div className="flex items-center justify-between">
        <div className="eyebrow text-[color:var(--coral)]">
          {coverSel.mode === "spine-title" || coverSel.mode === "spine-year"
            ? "Cover — Spine"
            : `Cover — ${zoneLabel}`}
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
          label="Accent color"
          value={cover.accent_color || ""}
          onChange={(v) => updateCover({ accent_color: v || null })}
          tid="cover-accent-color"
          onReset={() => updateCover({ accent_color: null })}
        />
        <ColorField
          label="Text color"
          value={cover.text_color || ""}
          onChange={(v) => updateCover({ text_color: v || null })}
          tid="cover-text-color"
          onReset={() => updateCover({ text_color: null })}
        />
      </div>

      {/* 2. ÉDITION DU TITRE PRINCIPAL */}
      {coverSel.mode === "title" && (
        <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-3">
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
              <option value="'Manrope', sans-serif">Manrope (sans)</option>
              <option value="Georgia, serif">Georgia</option>
              <option value="Helvetica, Arial, sans-serif">Helvetica</option>
              <option value="'Courier New', monospace">Courier</option>
            </select>
          </div>

          <div>
            <label className="eyebrow block mb-2">Title Size</label>
            <input
              type="range"
              min={20}
              max={120}
              value={cover.title_font_size || 48}
              onChange={(e) => updateCover({ title_font_size: Number(e.target.value) })}
              className="w-full"
              data-testid="cover-title-size"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              data-testid="cover-title-bold"
              onClick={() =>
                updateCover({
                  title_font_weight:
                    cover.title_font_weight === "bold" ||
                    cover.title_font_weight === "700" ||
                    cover.title_font_weight === "800"
                      ? "400"
                      : "bold",
                })
              }
              className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
                cover.title_font_weight === "bold" ||
                cover.title_font_weight === "700" ||
                cover.title_font_weight === "600" ||
                cover.title_font_weight === "800"
                  ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                  : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
              }`}
              title="Gras"
            >
              <Bold size={14} />
            </button>

            <button
              type="button"
              onClick={() =>
                updateCover({
                  title_x: 0.05,
                  title_y: 0.05,
                  title_w: 0.9,
                  title_h: 0.2,
                })
              }
              className="inline-flex items-center gap-1.5 px-3 py-2 border border-[color:var(--ink)]/30 text-xs font-semibold uppercase hover:border-[color:var(--ink)] transition-colors"
              title="Réinitialiser la position du titre"
            >
              <RotateCcw size={12} />
              Reset position
            </button>
          </div>
        </div>
      )}

      {/* 3. ÉDITION DE LA TRANCHE (SPINE TITLE / YEAR) */}
      {(coverSel.mode === "spine-title" || coverSel.mode === "spine-year") && (
        <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-3">
          <div className="eyebrow">
            {coverSel.mode === "spine-title" ? "Spine title" : "Spine year"}
          </div>

          {coverSel.mode === "spine-year" && updateAlbumYear && (
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

          <div>
            <label className="eyebrow block mb-2">Font</label>
            <select
              data-testid={
                coverSel.mode === "spine-title" ? "spine-title-font" : "spine-year-font"
              }
              value={
                (coverSel.mode === "spine-title"
                  ? cover.spine_title_font
                  : cover.spine_year_font) || "'Manrope', sans-serif"
              }
              onChange={(e) =>
                updateCover({
                  [coverSel.mode === "spine-title"
                    ? "spine_title_font"
                    : "spine_year_font"]: e.target.value,
                })
              }
              className="w-full border border-[color:var(--ink)]/20 p-2 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none"
            >
              <option value="'Baloo 2', sans-serif">Baloo (rounded)</option>
              <option value="'Manrope', sans-serif">Manrope (sans)</option>
              <option value="'Cormorant Garamond', serif">Cormorant (serif)</option>
              <option value="Georgia, serif">Georgia</option>
              <option value="Helvetica, Arial, sans-serif">Helvetica</option>
              <option value="'Courier New', monospace">Courier</option>
            </select>
          </div>

          <div>
            <label className="eyebrow block mb-2">Size</label>
            <input
              type="range"
              min={6}
              max={20}
              value={
                (coverSel.mode === "spine-title"
                  ? cover.spine_title_size
                  : cover.spine_year_size) || 9
              }
              onChange={(e) =>
                updateCover({
                  [coverSel.mode === "spine-title"
                    ? "spine_title_size"
                    : "spine_year_size"]: Number(e.target.value),
                })
              }
              className="w-full"
              data-testid={
                coverSel.mode === "spine-title" ? "spine-title-size" : "spine-year-size"
              }
            />
          </div>

          <button
            onClick={() =>
              updateCover({
                [coverSel.mode === "spine-title"
                  ? "spine_title_hidden"
                  : "spine_year_hidden"]: !(coverSel.mode === "spine-title"
                  ? cover.spine_title_hidden
                  : cover.spine_year_hidden),
              })
            }
            className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors"
            data-testid={
              coverSel.mode === "spine-title" ? "spine-title-toggle" : "spine-year-toggle"
            }
          >
            {(
              coverSel.mode === "spine-title"
                ? cover.spine_title_hidden
                : cover.spine_year_hidden
            ) ? (
              <Eye size={14} />
            ) : (
              <EyeOff size={14} />
            )}
            <span className="text-xs font-semibold tracking-widest uppercase">
              {(
                coverSel.mode === "spine-title"
                  ? cover.spine_title_hidden
                  : cover.spine_year_hidden
              )
                ? "Show"
                : "Hide"}
            </span>
          </button>
        </div>
      )}

      {/* 4. ÉDITION D'UN ÉLÉMENT SÉLECTIONNÉ (EXTRA ITEM) */}
      {selectedItem && (
        <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-3">
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
                <option value="Georgia, serif">Georgia</option>
                <option value="Helvetica, Arial, sans-serif">Helvetica</option>
                <option value="'Courier New', monospace">Courier</option>
              </select>
              <div className="flex items-center gap-2">
                <button
                  data-testid="cover-item-bold"
                  onClick={() =>
                    updateCoverItem(
                      selectedItem.id,
                      {
                        font_weight:
                          selectedItem.font_weight === "bold" ? "normal" : "bold",
                      },
                      side
                    )
                  }
                  className={`inline-flex items-center justify-center w-9 h-9 border ${
                    selectedItem.font_weight === "bold"
                      ? "bg-[color:var(--ink)] text-[color:var(--paper)]"
                      : "border-[color:var(--ink)]/30"
                  }`}
                >
                  <Bold size={14} />
                </button>
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
                <span className="text-xs w-8 text-right font-mono">
                  {selectedItem.font_size || selectedItem.fontSize || 22}px
                </span>
              </div>
              <input
                type="color"
                data-testid="cover-item-color"
                value={selectedItem.color || "#1A1A17"}
                onChange={(e) =>
                  updateCoverItem(selectedItem.id, { color: e.target.value }, side)
                }
                className="w-full h-9 border border-[color:var(--ink)]/20 cursor-pointer p-0"
              />
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