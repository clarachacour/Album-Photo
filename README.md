# Everbook — photo album app

People drop all their photos in bulk; the app picks the best ones (duplicates,
blur, dates, places), lays them out into a coffee-table book they can edit as a
flipbook, then exports a print-ready PDF and sends the order to the printer.

## Stack

| Part | Technology | Hosted on |
| --- | --- | --- |
| Frontend | React 19 built with Vite, React Router, Tailwind CSS, shadcn/ui, i18next (EN/FR) | Vercel |
| Backend | Python 3.11, FastAPI, Motor (async MongoDB) | Google Cloud Run (`backend/Dockerfile`) |
| Database | MongoDB | |
| Files | Cloudflare R2 (S3-compatible) | |
| PDF | Headless Chromium (Playwright) printing the React print page | Cloud Run |

## Repository layout

```
backend/    API — see backend/README.md for where each feature lives
frontend/   React app (pages in src/pages, reusable pieces in src/components)
memory/     Original product notes (PRD)
.github/    Automatic checks run by GitHub on every push
```

## Run it locally

You need Python 3.11, Node.js 22+ and a MongoDB (local or Atlas).

**Backend** (terminal 1)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env        # then fill in the values (JWT_SECRET is required)
uvicorn app.main:app --reload
```

**Frontend** (terminal 2)

```bash
cd frontend
npm install --legacy-peer-deps
cp .env.example .env        # REACT_APP_BACKEND_URL=http://localhost:8000
npm start
```

Then open http://localhost:3000.

## Tests

```bash
cd backend && pytest        # backend
cd frontend && npm test     # frontend
```

They also run automatically on GitHub for every push to `dev` and `main`
(tab **Actions** of the repository), along with a frontend build and lint.

## Branches and deployment

- `dev` — day-to-day work, deployed to the dev environment.
- `main` — production. Changes arrive from `dev` through a pull request.

Secrets (database, R2, SMTP, JWT…) are never committed: they are set as
environment variables on Cloud Run and Vercel. The full list, with
explanations, is in `backend/.env.example` and `frontend/.env.example`.

## Dependencies

- Backend: edit `backend/requirements.in`, then regenerate the pinned
  `backend/requirements.txt` (instructions at the top of `requirements.in`).
- Frontend: `npm install <package> --legacy-peer-deps`, and commit the updated
  `package-lock.json` with it.
