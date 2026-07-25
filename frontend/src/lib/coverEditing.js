import { api, coverAssetUrl } from "@/lib/api";
import { toast } from "sonner";

export function cryptoRandom() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `id-${Math.random().toString(36).slice(2, 10)}`;
}

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
      const items = (cover[key] || []).map((it) => {
        if (it.id !== itemId) return it;

        let updatedPatch = { ...patch };

        // ----------------------------------------------------
        // LOGIQUE DE MAGNÉTISME ET CENTRAGE (SNAP TO CENTER)
        // ----------------------------------------------------
        const SNAP_THRESHOLD = 0.02; // Marge de magnétisme (2%)

        const currentW = updatedPatch.w ?? it.w ?? 0;
        const currentH = updatedPatch.h ?? it.h ?? 0;

        // Si on déplace X
        if (updatedPatch.x !== undefined) {
          const centerX = updatedPatch.x + currentW / 2;
          // Si le centre de l'objet est à moins de 2% du centre de la page (0.5)
          if (Math.abs(centerX - 0.5) < SNAP_THRESHOLD) {
            updatedPatch.x = 0.5 - currentW / 2; // Calage parfait au centre
            updatedPatch.isCenteredX = true;     // Flag pour afficher la ligne verticale
          } else {
            updatedPatch.isCenteredX = false;
          }
        }

        // Si on déplace Y
        if (updatedPatch.y !== undefined) {
          const centerY = updatedPatch.y + currentH / 2;
          // Si le centre de l'objet est à moins de 2% du centre de la page (0.5)
          if (Math.abs(centerY - 0.5) < SNAP_THRESHOLD) {
            updatedPatch.y = 0.5 - currentH / 2; // Calage parfait au centre
            updatedPatch.isCenteredY = true;     // Flag pour afficher la ligne horizontale
          } else {
            updatedPatch.isCenteredY = false;
          }
        }

        return { ...it, ...updatedPatch };
      });

      const next = { ...prev, cover: { ...cover, [key]: items } };

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