FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright needs its browser binary AND a set of OS-level libraries
# (fonts, graphics libs, etc.) to run headless Chromium — --with-deps
# installs both in one step, matching whatever's actually needed for the
# installed Playwright version.
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000
# Shell form (not exec-array form) is required here so $PORT actually gets
# substituted — Cloud Run injects PORT=8080 and expects the container to
# listen on it; platforms that don't set it (e.g. Render) fall back to 8000.
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
