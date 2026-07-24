import { api, coverAssetUrl } from "@/lib/api";
import { toast } from "sonner";

export function cryptoRandom() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `id-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * All the cover-editing actions (colors, title text, extra items on the
 * front/back, logo upload/replace) in one place, so the creation wizard's
 * "Edit" step and the post-creation book editor behave identically.
 *
 * `albumId` is required for image uploads (they need a real album to attach
 * the file to) — pass the freshly created album's id.
 */
export function makeCoverEditingActions({ setAlbum, albumId, coverSel, setCoverSel }) {
  const updateCover = (patch) => {
    setAlbum((prev) => ({ ...prev, cover: { ...(prev.cover || {}), ...patch } }));
  };

  const updateAlbumTitle = (newTitle) => {
    setAlbum((prev) => ({ ...prev, title: newTitle }));
  };

  const updateCoverItem = (itemId, patch, side = coverSel?.side || "front") => {
    const key = side === "back" ? "back_extra_items" : "extra_items";
    setAlbum((prev) => {
      const cover = prev.cover || {};
      const items = (cover[key] || []).map((it) => (it.id === itemId ? { ...it, ...patch } : it));
      return { ...prev, cover: { ...cover, [key]: items } };
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
      const imageUrl = coverAssetUrl(data.storage_path);
      if (replaceItemId) {
        updateCoverItem(replaceItemId, { image_url: imageUrl, storage_path: data.storage_path, asset: null }, side);
        toast.success("Image remplacée");
      } else {
        const newItem = {
          id: cryptoRandom(),
          type: "image",
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

  return { updateCover, updateAlbumTitle, updateCoverItem, addCoverText, addCoverShape, addCoverImage, removeCoverItem };
}