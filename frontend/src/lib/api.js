import axios from "axios";

const BACKEND_URL = (import.meta.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("album_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Direct links to the photos in R2, sent with the album's photos (see
// signed_urls.py on the server): kept here so every image on the page uses
// them, whichever component shows it.
const photoLinks = new Map();

export function rememberPhotoLinks(photos) {
  for (const p of photos || []) {
    if (p?.id && p.urls) photoLinks.set(p.id, p.urls);
  }
}

api.interceptors.response.use(
  (r) => {
    if (Array.isArray(r?.data?.photos)) rememberPhotoLinks(r.data.photos);
    return r;
  },
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("album_token");
      localStorage.removeItem("album_user");
    }
    return Promise.reject(err);
  }
);

export function getToken() {
  return localStorage.getItem("album_token");
}

export function photoImageUrl(photoId, variant = "thumb") {
  // Straight from R2 when there's a link still valid for at least an hour;
  // otherwise through our server (a size not made yet, a page left open
  // for days…).
  const links = photoLinks.get(photoId);
  if (links?.[variant] && Date.parse(links.expires_at) - Date.now() > 3600 * 1000) return links[variant];
  const t = getToken();
  return `${API}/photos/${photoId}/image?auth=${encodeURIComponent(t || "")}&variant=${variant}`;
}

export function pdfExportUrl(albumId) {
  const t = getToken();
  return `${API}/albums/${albumId}/export?auth=${encodeURIComponent(t || "")}`;
}

export function coverImageUrl(albumId, version = 0, variant = "thumb") {
  const t = getToken();
  return `${API}/albums/${albumId}/cover-image?auth=${encodeURIComponent(t || "")}&v=${version}&variant=${variant}`;
}

export function coverAssetUrl(storagePath, variant = "thumb") {
  const t = getToken();
  return `${API}/cover-assets/image?path=${encodeURIComponent(storagePath)}&auth=${encodeURIComponent(t || "")}&variant=${variant}`;
}

/**
 * Address of an image placed on the cover, built when it's displayed. The
 * address saved with the album contains the sign-in key of the day it was
 * added, which expires after 30 days (and the print page has its own key):
 * rebuild it from the file's storage path with the current key.
 */
export function coverItemImageSrc(item, variant = "original") {
  if (item?.storage_path) return coverAssetUrl(item.storage_path, variant);
  const url = item?.image_url;
  if (!url) return null;
  const query = url.split("/cover-assets/image?")[1];
  const path = query && new URLSearchParams(query).get("path");
  return path ? coverAssetUrl(path, variant) : url; // images built into templates (data: URLs) as is
}

export function adminOrderPdfUrl(orderId) {
  const t = getToken();
  return `${API}/admin/orders/${orderId}/pdf?auth=${encodeURIComponent(t || "")}`;
}
