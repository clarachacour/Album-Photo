import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * Saving the album in the editor, built so a weak or dropped connection
 * never loses an edit:
 *
 * - Saved automatically a few seconds after the last change.
 * - A failed save is tried again when the connection comes back, or every
 *   20 seconds.
 * - Until the server has them, the edits are also kept on this device
 *   (localStorage). If the page is closed or crashes first, they're offered
 *   back the next time the album is opened — only if the album hasn't
 *   changed on the server since (new pages from added photos, a save from
 *   another device…), so a stale copy never overwrites newer work.
 * - The browser warns before leaving the page with unsaved edits.
 *
 * status: "saved" | "unsaved" | "saving" | "offline" | "error" | "locked"
 */

const AUTOSAVE_DELAY_MS = 4000;
const RETRY_DELAY_MS = 20000;

// What the editor changes, and what a save sends.
export function editableContent(album) {
  return {
    title: album.title,
    country: album.country,
    year: album.year,
    pages: album.pages,
    cover: album.cover || {},
  };
}

const draftKey = (id) => `everbook_unsaved_${id}`;
function readDraft(id) {
  try {
    return JSON.parse(localStorage.getItem(draftKey(id)) || "null");
  } catch {
    return null;
  }
}
function writeDraft(id, draft) {
  try {
    localStorage.setItem(draftKey(id), JSON.stringify(draft));
  } catch {
    /* storage full or unavailable: the server save still happens */
  }
}
function clearDraft(id) {
  try {
    localStorage.removeItem(draftKey(id));
  } catch {
    /* unavailable */
  }
}

export function useAlbumSaving({ albumId, album, autosave }) {
  const [status, setStatus] = useState("saved");
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine !== false));
  // Edits found on this device from a previous visit, offered back.
  const [recovered, setRecovered] = useState(null);

  const savedJsonRef = useRef(null); // content known to be on the server
  const baseRef = useRef(null); // the server's updated_at that content matches
  const albumRef = useRef(album);
  albumRef.current = album;
  const lockedRef = useRef(false);

  const currentJson = album ? JSON.stringify(editableContent(album)) : null;
  const dirty = Boolean(album && savedJsonRef.current !== null && currentJson !== savedJsonRef.current);

  /** The album as it is on the server (just loaded, or reloaded). */
  const markLoaded = useCallback(
    (data) => {
      savedJsonRef.current = JSON.stringify(editableContent(data));
      baseRef.current = data.updated_at || null;
      lockedRef.current = false;
      setStatus("saved");
      const draft = readDraft(albumId);
      if (draft && draft.base === baseRef.current && JSON.stringify(draft.content) !== savedJsonRef.current) {
        setRecovered(draft.content);
      } else {
        clearDraft(albumId);
        setRecovered(null);
      }
    },
    [albumId]
  );

  // One save at a time: a save asked for while another is on its way runs
  // right after it, with the edits made in between.
  const chainRef = useRef(Promise.resolve());
  const saveNow = useCallback(async () => {
    const current = albumRef.current;
    if (!current || lockedRef.current) return lockedRef.current ? "locked" : "failed";
    const content = editableContent(current);
    const json = JSON.stringify(content);
    if (json === savedJsonRef.current) return "saved";
    setStatus("saving");
    try {
      const { data } = await api.patch(`/albums/${albumId}`, content);
      savedJsonRef.current = json;
      baseRef.current = data?.updated_at || baseRef.current;
      setLastSavedAt(new Date());
      const latest = albumRef.current ? editableContent(albumRef.current) : content;
      if (JSON.stringify(latest) !== json) writeDraft(albumId, { base: baseRef.current, content: latest });
      else clearDraft(albumId);
      setStatus("saved");
      return "saved";
    } catch (err) {
      if (err?.response?.status === 403) {
        lockedRef.current = true; // ordered in the meantime: can't be changed any more
        setStatus("locked");
        return "locked";
      }
      setStatus(navigator.onLine === false ? "offline" : "error");
      return "failed";
    }
  }, [albumId]);

  /** Saves now; resolves to "saved", "failed" or "locked". */
  const save = useCallback(() => {
    const run = chainRef.current.then(saveNow);
    chainRef.current = run.catch(() => {});
    return run;
  }, [saveNow]);

  // Keep a copy on this device while the server doesn't have the edits.
  useEffect(() => {
    if (!album || savedJsonRef.current === null) return;
    if (!dirty) return;
    const timer = setTimeout(() => writeDraft(albumId, { base: baseRef.current, content: editableContent(album) }), 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentJson]);

  // Save a few seconds after the last change.
  useEffect(() => {
    if (!autosave || !dirty || lockedRef.current) return;
    const timer = setTimeout(save, AUTOSAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [autosave, dirty, currentJson, save]);

  // A failed save: try again every 20 s, and as soon as the connection is back.
  useEffect(() => {
    if (status !== "error" && status !== "offline") return;
    const timer = setInterval(() => navigator.onLine !== false && save(), RETRY_DELAY_MS);
    return () => clearInterval(timer);
  }, [status, save]);

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      if (JSON.stringify(editableContent(albumRef.current || {})) !== savedJsonRef.current) save();
    };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [save]);

  // Leaving with edits the server doesn't have yet.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const dismissRecovered = useCallback(() => {
    clearDraft(albumId);
    setRecovered(null);
  }, [albumId]);

  return { status: dirty && status === "saved" ? "unsaved" : status, dirty, online, lastSavedAt, save, markLoaded, recovered, dismissRecovered, clearRecovered: () => setRecovered(null) };
}
