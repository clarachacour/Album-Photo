FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright needs its browser binary AND a set of OS-level libraries
# (fonts, graphics libs, etc.) to run headless Chromium — --with-deps
# installs both in one step, matching whatever's actually needed for the
# installed Playwright version.
RUN playwright install --with-deps chromium

# Face detection model (YuNet, ~230KB) — used to keep the AI layout from
# cropping people's heads/faces out of a photo, by centering the crop on
# detected faces instead of the raw photo center. Runs entirely locally in
# this container (no photo ever leaves the server for this) — see
# compute_face_focal_point() in server.py. Sourced from KDE's digiKam
# mirror rather than the upstream opencv_zoo repo directly, since that
# repo's own Git LFS bandwidth is currently exhausted; sha256sum below
# pins it to the exact same file (verified against the official release).
RUN curl -fsSL -o /app/face_detection_yunet.onnx \
      https://files.kde.org/digikam/facesengine/yunet/face_detection_yunet_2023mar.onnx \
    && echo "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  /app/face_detection_yunet.onnx" | sha256sum -c -

COPY . .

EXPOSE 8000
# Shell form (not exec-array form) is required here so $PORT actually gets
# substituted — Cloud Run injects PORT=8080 and expects the container to
# listen on it; platforms that don't set it (e.g. Render) fall back to 8000.
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
