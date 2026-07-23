import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
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

export function photoImageUrl(photoId) {
  const t = getToken();
  return `${API}/photos/${photoId}/image?auth=${encodeURIComponent(t || "")}`;
}

export function pdfExportUrl(albumId) {
  const t = getToken();
  return `${API}/albums/${albumId}/export?auth=${encodeURIComponent(t || "")}`;
}

export function coverImageUrl(albumId, version = 0) {
  const t = getToken();
  return `${API}/albums/${albumId}/cover-image?auth=${encodeURIComponent(t || "")}&v=${version}`;
}
