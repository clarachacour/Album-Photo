# Fable Studio · Album AI Studio — PRD

## Problem Statement
Build an application that lets a user create a photo album. The user drops all their photos in bulk (unordered, duplicates allowed). An AI selects, sorts and orders the photos, and generates a coffee-table style album with intelligent, varied page layouts. First step: choose a cover template (coffee-table book style: solid color + illustration + title on front, same title + year on spine, country on back). Then choose album size (A4/A5) and orientation (portrait/landscape). Upload photos. AI processes in background. Preview the album as a 3D flipbook (two facing pages, click to flip). User can edit images (position, size), add/remove text (font, color, size). Finally export to a print-ready PDF.

## User Choices
- **AI model**: Gemini 3 Flash via Emergent Universal Key
- **Storage**: Emergent Object Storage
- **Auth**: Email/Password (JWT + bcrypt)
- **Cover templates**: 6 (teal-coral, sand-forest, navy-blush, terracotta-cream, forest-gold, charcoal-rose)
- **MVP scope**: simple — drag & drop, basic text editing (font/color/size), PDF export

## Architecture
- **Backend**: FastAPI (Python) at `/api/*` on port 8001
  - MongoDB via Motor (async)
  - JWT auth (`/api/auth/signup`, `/api/auth/login`, `/api/auth/me`)
  - Album CRUD (`/api/albums`, `/api/albums/{id}`, PATCH, DELETE)
  - Photo upload (multipart) — stored on Emergent Object Storage
  - Photo image proxy (`/api/photos/{id}/image?auth=TOKEN`)
  - AI processing (`/api/albums/{id}/process` runs in background)
  - Status polling (`/api/albums/{id}/status`)
  - PDF export (ReportLab, `/api/albums/{id}/export?auth=TOKEN`)
- **Frontend**: React 19 + React Router
  - Pages: Landing, AuthPage, Dashboard, CreateAlbum wizard, AlbumEditor (flipbook)
  - Library: react-pageflip for 3D flipbook, dnd-kit (added), lucide-react icons, sonner toasts
  - Typography: Cormorant Garamond (display) + Manrope (UI)
  - Colors: Paper (#F9F8F6), Ink (#1A1A17), Coral (#E56B55), Teal (#0F5A67)

## Implemented (2026-02)
- Editorial landing page (marketing) with cover template gallery
- Signup / Login with JWT
- Dashboard listing user's albums
- 4-step album creation wizard (cover → format → details → photos)
- AI processing screen with staged messages
- 3D flipbook preview (react-pageflip)
- Text tool: add / edit / delete text (font, color, size, position)
- Save album layout
- Export PDF via ReportLab (cover + content pages + back)

## Next Action Items (Backlog)
- **P1**: Photo drag & drop reorder between pages
- **P1**: Photo resize/crop within a slot
- **P1**: Regenerate a specific page layout
- **P2**: Duplicate detection with visual review before commit
- **P2**: Google Auth alternative
- **P2**: Public share link (view-only)
- **P2**: Album cover custom image upload
- **P2**: Print-and-ship integration (revenue: partner with a print-on-demand service like Blurb/Peecho)
