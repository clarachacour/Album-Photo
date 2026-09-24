# Backend (FastAPI)

API of the album app: accounts, albums, photos, curation, PDF export and orders.
Data lives in MongoDB, files in Cloudflare R2, and it runs on Cloud Run
(see `Dockerfile`).

## Where things are

```
backend/
  app/
    main.py          Creates the app, plugs in the routers, startup/shutdown, CORS
    config.py        Every environment variable, in one place
    db.py            MongoDB connection
    schemas.py       Shape of request bodies / responses (Pydantic)
    core/            Cross-cutting building blocks
      auth.py          Passwords, login tokens, "current user", admin check
      security.py      JWT secret check, CORS list, rate limiter
      rate_limit.py    Limits applied to login / forgot-password / contact
      signed_links.py  Signed links in the printer & delivery emails
      executors.py     Thread pools for blocking work (R2, photos, PDF)
    routers/         HTTP endpoints only: read the request, call services, answer
      auth.py  albums.py  photos.py  covers.py  mobile_upload.py
      orders.py  admin.py  contact.py  internal.py  health.py
    services/        The actual work, reusable by several routers
      storage.py       R2 files          email.py        Every email sent
      photos.py        Upload & resizing curation.py     Duplicates, sharpness, faces
      layout.py        Page layouts      processing.py   Curation + layout pipeline
      pdf.py           Browser PDF export pdf_legacy.py  ReportLab fallback export
      orders.py        Statuses, order PDF generation    pricing.py  Prices
      google_photos.py Google Photos import              albums.py   Shared album rules
    assets/          Fonts and images embedded in code (generated, do not edit by hand)
  tests/
  server.py          Only kept so `uvicorn server:app` still works
```

Rule of thumb: a **router** never does heavy work itself, it calls a
**service**. A **service** never imports a router.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then fill in the values
uvicorn app.main:app --reload
```

The API is then on http://localhost:8000/api/ and the interactive docs on
http://localhost:8000/docs.

## Tests

```bash
cd backend
pytest tests/test_security.py tests/test_units.py tests/test_api.py
```

They need no database, network or R2: MongoDB is replaced by an in-memory
fake (see `tests/conftest.py`). They also run automatically on GitHub for
every push (`.github/workflows/backend-tests.yml`).
