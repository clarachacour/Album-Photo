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

api.interceptors.response.use(
  (r) => r,
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
