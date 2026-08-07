import { api, coverAssetUrl } from "@/lib/api";
import { toast } from "sonner";

export function cryptoRandom() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `id-${Math.random().toString(36).slice(2, 10)}`;
}

const SNAP_THRESHOLD = 0.02; // 2% of the page — how close counts as "aligned"

// Finds the best-matching guide line for one axis: checks the item's start,
// center and end against the page center plus every sibling's start, center
// and end. Returns the (possibly snapped) position and the guide's location
// (for drawing the line), or leaves the position untouched if nothing lines up.
function findSnap(pos, size, siblings, axis) {
  const sizeKey = axis === "x" ? "w" : "h";
  const candidates = [0.5];
  for (const s of siblings) {
    if (s[axis] == null || s[sizeKey] == null) continue;
    candidates.push(s[axis], s[axis] + s[sizeKey] / 2, s[axis] + s[sizeKey]);
  }
  const points = [
    { edge: "start", value: pos },
    { edge: "center", value: pos + size / 2 },
    { edge: "end", value: pos + size },
  ];
  let best = null;
  for (const c of candidates) {
    for (const p of points) {
      const diff = Math.abs(p.value - c);
      if (diff < SNAP_THRESHOLD && (!best || diff < best.diff)) {
        const newPos = p.edge === "start" ? c : p.edge === "center" ? c - size / 2 : c - size;
        best = { diff, guide: c, newPos };
      }
    }
  }
  if (best) return { value: best.newPos, guide: best.guide };
  return { value: pos, guide: null };
}

export function computeAlignSnap(pos, size, siblings, axis) {
  return findSnap(pos, size, siblings || [], axis);
}

export function makeCoverEditingActions({ setAlbum, albumId, coverSel, setCoverSel }) {
  const updateCover = (patch) => {
    setAlbum((prev) => ({ ...prev, cover: { ...(prev.cover || {}), ...patch } }));
  };

  // The front-cover title is dragged/resized like any other item (raw {x,y}
  // or {w,h} patches from DraggableItem), but it's stored under dedicated
  // title_x/title_y/title_w/title_h fields on `cover` — this maps between
  // the two and applies the same center-snapping as other elements.
  const updateCoverTitle = (patch) => {
    setAlbum((prev) => {
      const cover = prev.cover || {};
      const w = patch.w ?? cover.title_w ?? 0.84;
      const h = patch.h ?? cover.title_h ?? 0.28;
      const siblings = cover.extra_items || [];
      const mapped = {};
      if (patch.x !== undefined) {
        const s = computeAlignSnap(patch.x, w, siblings, "x");
        mapped.title_x = s.value;
        mapped.align_guide_x = s.guide;
      }
      if (patch.y !== undefined) {
        const s = computeAlignSnap(patch.y, h, siblings, "y");
        mapped.title_y = s.value;
        mapped.align_guide_y = s.guide;
      }
      if (patch.w !== undefined) mapped.title_w = patch.w;
      if (patch.h !== undefined) mapped.title_h = patch.h;
      return { ...prev, cover: { ...cover, ...mapped } };
    });
  };

  const updateAlbumTitle = (newTitle) => {
    setAlbum((prev) => ({ ...prev, title: newTitle }));
  };

  const updateAlbumYear = (newYear) => {
    const y = parseInt(newYear, 10);
    setAlbum((prev) => ({ ...prev, year: Number.isNaN(y) ? prev.year : y }));
  };

  const updateCoverItem = (itemId, patch, side = coverSel?.side || "front") => {
    const key = side === "back" ? "back_extra_items" : "extra_items";

    setAlbum((prev) => {
      const cover = prev.cover || {};
      const siblings = (cover[key] || []).filter((it) => it.id !== itemId);
      if (side === "front") {
        siblings.push({ x: cover.title_x ?? 0.08, y: cover.title_y ?? 0.08, w: cover.title_w ?? 0.84, h: cover.title_h ?? 0.28 });
      }
      let guideX = null, guideY = null;
      const items = (cover[key] || []).map((it) => {
        if (it.id !== itemId) return it;

        const updatedPatch = { ...patch };
        const currentW = updatedPatch.w ?? it.w ?? 0;
        const currentH = updatedPatch.h ?? it.h ?? 0;

        if (updatedPatch.x !== undefined) {
          const s = computeAlignSnap(updatedPatch.x, currentW, siblings, "x");
          updatedPatch.x = s.value;
          guideX = s.guide;
        }
        if (updatedPatch.y !== undefined) {
          const s = computeAlignSnap(updatedPatch.y, currentH, siblings, "y");
          updatedPatch.y = s.value;
          guideY = s.guide;
        }

        return { ...it, ...updatedPatch };
      });

      const next = { ...prev, cover: { ...cover, [key]: items, align_guide_x: guideX, align_guide_y: guideY } };

      if (patch.content !== undefined) {
        const updated = items.find((it) => it.id === itemId);
        if (updated?.role === "country") {
          next.country = patch.content;
        } else if (updated?.role === "year") {
          const y = parseInt(patch.content, 10);
          if (!Number.isNaN(y)) next.year = y;
        }
      }
      return next;
    });

    setCoverSel((prev) => (prev && prev.mode === "item" && prev.itemId === itemId ? { ...prev } : prev));
  };

  const addCoverText = (content = "Nouveau texte", side = coverSel?.side || "front") => {
    const key = side === "back" ? "back_extra_items" : "extra_items";
    const newItem = {
      id: cryptoRandom(),
      type: "text",
      content,
      x: 0.1,
      y: 0.5,
      w: 0.5,
      h: 0.08,
      font: "'Manrope', sans-serif",
      font_size: 22,
      font_weight: "normal",
    };
    setAlbum((prev) => {
      const cover = prev.cover || {};
      newItem.color = cover.text_color || "#F9F8F6";
      return { ...prev, cover: { ...cover, [key]: [...(cover[key] || []), newItem] } };
    });
    setCoverSel({ mode: "item", side, itemId: newItem.id });
    toast.success("Texte ajouté à la couverture");
  };

  const addCoverShape = (shape_type = "rect", side = coverSel?.side || "front") => {
    const key = side === "back" ? "back_extra_items" : "extra_items";
    const newItem = {
      id: cryptoRandom(),
      type: "shape",
      shape_type,
      x: 0.3,
      y: 0.6,
      w: 0.15,
      h: 0.15,
    };
    setAlbum((prev) => {
      const cover = prev.cover || {};
      newItem.fill_color = cover.accent_color || "#E56B55";
      return { ...prev, cover: { ...cover, [key]: [...(cover[key] || []), newItem] } };
    });
    setCoverSel({ mode: "item", side, itemId: newItem.id });
    toast.success("Forme ajoutée");
  };

  const addCoverImage = async (file, replaceItemId = null, side = coverSel?.side || "front") => {
    if (!file || !albumId) return;
    const key = side === "back" ? "back_extra_items" : "extra_items";
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/albums/${albumId}/cover-assets`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      // Stored permanently on the cover item and reused later by the PDF
      // export — must stay full resolution, unlike normal on-screen photo
      // display which defaults to the thumbnail.
      const imageUrl = coverAssetUrl(data.storage_path, "original");
      if (replaceItemId) {
        updateCoverItem(replaceItemId, { image_url: imageUrl, storage_path: data.storage_path, asset: null }, side);
        toast.success("Image remplacée");
      } else {
        const newItem = {
          id: cryptoRandom(),
          type: "image",
          is_photo: true,
          x: 0.28,
          y: 0.42,
          w: 0.44,
          h: 0.4,
          image_url: imageUrl,
          storage_path: data.storage_path,
        };
        setAlbum((prev) => {
          const cover = prev.cover || {};
          return { ...prev, cover: { ...cover, [key]: [...(cover[key] || []), newItem] } };
        });
        setCoverSel({ mode: "item", side, itemId: newItem.id });
        toast.success("Image ajoutée à la couverture");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur lors de l'upload de l'image");
    }
  };

  const removeCoverItem = (itemId, side = coverSel?.side || "front") => {
    const key = side === "back" ? "back_extra_items" : "extra_items";
    setAlbum((prev) => {
      const cover = prev.cover || {};
      return {
        ...prev,
        cover: { ...cover, [key]: (cover[key] || []).filter((it) => it.id !== itemId) },
      };
    });
    setCoverSel(null);
  };

  return { updateCover, updateCoverTitle, updateAlbumTitle, updateAlbumYear, updateCoverItem, addCoverText, addCoverShape, addCoverImage, removeCoverItem };
}