import React, { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, coverImageUrl } from "@/lib/api";
import { getTemplate } from "@/lib/coverTemplates";
import { CoverFrontPage, CoverBackPage, AlbumPage } from "@/components/AlbumPage";
import { CoverSpine } from "@/components/CoverSpine";
import { pageDimsMm, spineWidthMm } from "@/lib/printDims";

/**
 * Renders the whole album — front cover + spine, interior pages, back cover
 * — as a sequence of full-physical-size pages, one per print sheet. This is
 * meant to be opened by a headless browser (Playwright) on the backend and
 * captured with page.pdf(), so the exported PDF is pixel-identical to what
 * this same React code already renders in the flipbook — no separate
 * hand-written PDF drawing logic to keep in sync.
 */
export default function PrintAlbum() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const [album, setAlbum] = useState(null);
  const [error, setError] = useState(null);
  // Set with a short delay after the album loads, rather than the instant
  // it does — every page (title, subtitle, spine text, etc.) auto-fits its
  // font size via its own layout effect, several of which wait on a web
  // font to finish loading before recomputing a final value. Signaling
  // "ready" the moment React's first render pass completes let Playwright
  // occasionally capture a page mid-calculation — most visibly, a subtitle
  // sized from a stale/incomplete measurement, clipped in the exported
  // PDF despite looking correct in the flipbook (which has no such rush).
  const [printReady, setPrintReady] = useState(false);

  useEffect(() => {
    const token = searchParams.get("auth");
    if (token) {
      // The api client reads its bearer token from localStorage — this is a
      // fresh, isolated browser context (headless print run), so writing it
      // here is safe and doesn't touch any real user's session.
      localStorage.setItem("album_token", token);
    }
    (async () => {
      try {
        const { data } = await api.get(`/albums/${id}`);
        setAlbum(data);
      } catch (e) {
        setError(e?.response?.data?.detail || "Failed to load album");
      }
    })();
  }, [id, searchParams]);

  useEffect(() => {
    if (!album) return;
    const t = setTimeout(() => setPrintReady(true), 1200);
    return () => clearTimeout(t);
  }, [album]);

  if (error) return <div data-print-error="true">{error}</div>;
  if (!album) return <div>Loading…</div>;

  const template = getTemplate();
  const { w: pw, h: ph } = pageDimsMm(album.size, album.orientation);
  const spineMm = spineWidthMm((album.pages || []).length);
  const seamMm = 0.8; // thin visible gap between spine and cover, matching the flipbook
  const cover = album.cover || {};

  return (
    <div data-print-ready={printReady ? "true" : undefined}>
      <style>{`
        @page cover-sheet { size: ${pw + spineMm + seamMm}mm ${ph}mm; margin: 0; }
        @page content-sheet { size: ${pw}mm ${ph}mm; margin: 0; }
        body { margin: 0; }
        .print-page {
          position: relative;
          overflow: hidden;
          page-break-after: always;
          break-after: page;
        }
        /* The last sheet (back cover) shouldn't force a page break after
           itself — there's nothing left to follow it, so doing so left a
           trailing blank page at the end of every exported PDF. */
        .print-page:last-child {
          page-break-after: auto;
          break-after: auto;
        }
        .cover-sheet { page: cover-sheet; }
        .content-sheet { page: content-sheet; }
      `}</style>

      {/* Front cover + spine, side by side on one sheet, with a thin seam
          between them (matching the flipbook) so it's clear they're two
          distinct pieces rather than one continuous surface. */}
      <div className="print-page cover-sheet" style={{ width: `${pw + spineMm + seamMm}mm`, height: `${ph}mm`, display: "flex" }}>
        <div style={{ width: `${spineMm}mm`, height: `${ph}mm`, flexShrink: 0 }}>
          <CoverSpine title={album.title} year={album.year} template={template} cover={cover} editable={false} />
        </div>
        <div style={{ width: `${seamMm}mm`, height: `${ph}mm`, flexShrink: 0, background: "rgba(26,26,23,0.7)" }} />
        <div style={{ width: `${pw}mm`, height: `${ph}mm` }}>
          <CoverFrontPage
            template={template}
            title={album.title}
            orientation={album.orientation}
            coverImageUrl={album.cover_image_path ? coverImageUrl(album.id, 0, "original") : undefined}
            cover={cover}
            editable={false}
          />
        </div>
      </div>

      {/* Interior pages */}
      {(album.pages || []).map((page, i) => (
        <div key={page.id || i} className="print-page content-sheet" style={{ width: `${pw}mm`, height: `${ph}mm` }}>
          <AlbumPage page={page} orientation={album.orientation} pageIndex={i} editable={false} highRes />
        </div>
      ))}

      {/* Back cover */}
      <div className="print-page content-sheet" style={{ width: `${pw}mm`, height: `${ph}mm` }}>
        <CoverBackPage
          template={template}
          country={album.country}
          year={album.year}
          orientation={album.orientation}
          cover={cover}
          editable={false}
        />
      </div>
    </div>
  );
}
