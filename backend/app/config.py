"""Every setting read from environment variables, in one place."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.security import load_jwt_secret, parse_cors_origins

# backend/ (the folder that contains app/): where .env and the face
# detection model live.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------- Config ----------
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
# Required: the app refuses to start without a real secret (see
# security.load_jwt_secret) — a guessable default would let anyone forge a
# login token for any account.
JWT_SECRET = load_jwt_secret(os.environ.get('JWT_SECRET'))
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXP_HOURS = 24 * 30
APP_NAME = os.environ.get('APP_NAME', 'albumai')
# The only account allowed to see every customer's orders (name, address,
# phone, which album, the print-ready PDF, and now status changes) — set
# this to your own account's email as a Cloud Run environment variable.
# Left unset, the admin endpoints below refuse everyone rather than
# silently exposing customer data to any logged-in user.
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
# How many photos get processed at once (uploads) / analyzed at once (AI).
# Each one held in memory means the *decoded* image, not just the file size
# — a single 12MP JPEG can take 30-50MB once decoded. On a small instance
# (e.g. Render's 512MB Starter plan), running 8 at once was enough to run
# out of memory on a batch of ordinary phone photos. Lower default here,
# safely raise via env var once on a larger instance — no code change needed.
UPLOAD_CONCURRENCY = int(os.environ.get("UPLOAD_CONCURRENCY", "3"))
AI_CONCURRENCY = int(os.environ.get("AI_CONCURRENCY", "3"))
# Deliberately separate from — and lower than — UPLOAD_CONCURRENCY: this
# one bounds simultaneous connections to Google's own servers (Google
# Photos import), not our own R2 bucket, and pushing it as high as
# UPLOAD_CONCURRENCY caused Google to start dropping connections
# (SSLEOFError / "Max retries exceeded") under load.
GOOGLE_PHOTOS_CONCURRENCY = int(os.environ.get("GOOGLE_PHOTOS_CONCURRENCY", "4"))
# How many ambiguous-duplicate-cluster resolutions (each a Gemini API call,
# see _resolve_ambiguous_cluster_with_ai) run at once during curation.
# Bounded, not unlimited — these are calls to an external API we don't
# control the rate limits of, same reasoning as GOOGLE_PHOTOS_CONCURRENCY
# above.
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", "8"))
# How many PDF generations can genuinely run at once, service-wide (see
# _acquire_pdf_generation_slot, which enforces this via a shared MongoDB
# collection rather than an in-process counter, so it applies regardless of
# which Cloud Run instance each request lands on). Each generation's peak
# memory is bounded *per generation* by chunking and incremental merging,
# but that bound doesn't prevent two or three running at once on the same
# instance from stacking their peaks — this instance's memory was already
# raised once specifically because a single 100-page album's render came
# close to OOM-killing it, so raising this past a small number without also
# watching real memory usage under actual overlap risks recreating that
# exact problem, just with concurrent generations instead of one large one.
MAX_CONCURRENT_PDF_GENERATIONS = int(os.environ.get("MAX_CONCURRENT_PDF_GENERATIONS", "2"))

# Optional — the AI-assisted duplicate resolution in curate_photos only
# runs when this is set. Without it, curation stays 100% classical (phash +
# sharpness), same as before. Get a key from Google AI Studio
# (aistudio.google.com/apikey) and set GEMINI_API_KEY on Cloud Run to
# enable it. Deliberately the cheapest current vision-capable model — this
# is called on a handful of ambiguous clusters per album, not per photo, so
# the extra reasoning power of a bigger model isn't worth the cost here.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
# Shared secret Cloud Scheduler must send to trigger the 30-day draft-album
# purge (see /internal/cleanup-expired-albums) — without it, anyone who
# finds the URL could wipe every never-ordered album on demand.
CLEANUP_SECRET = os.environ.get("CLEANUP_SECRET")
# Order PDFs are generated through a Google Cloud Tasks queue
# (projects/<project>/locations/<region>/queues/<name>): the order is
# confirmed at once, the queue calls /api/internal/orders/<id>/generate-pdf
# (authenticated with CLEANUP_SECRET) and retries it if it fails. Unset:
# the PDF is generated during the order request, as before.
PDF_TASKS_QUEUE = os.environ.get("PDF_TASKS_QUEUE")
# Must match the queue's "max attempts": the admin gets the failure email
# only after the last one.
PDF_TASK_MAX_ATTEMPTS = int(os.environ.get("PDF_TASK_MAX_ATTEMPTS", "3"))
DRAFT_ALBUM_RETENTION_DAYS = int(os.environ.get("DRAFT_ALBUM_RETENTION_DAYS", "30"))
# Daily database backups (POST /internal/backup) kept in R2 for this many days.
BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
# First nudge once an album has sat untouched this many days; the second,
# stronger warning fires this many days before the purge above actually
# deletes it (see /internal/remind-unfinished-albums).
UNFINISHED_ALBUM_REMINDER_DAYS = int(os.environ.get("UNFINISHED_ALBUM_REMINDER_DAYS", "3"))
ALBUM_EXPIRING_WARNING_DAYS_BEFORE = int(os.environ.get("ALBUM_EXPIRING_WARNING_DAYS_BEFORE", "5"))
# A cart left with albums in it, untouched for this many hours: one
# reminder email (again only if the cart changes afterwards).
CART_REMINDER_HOURS = int(os.environ.get("CART_REMINDER_HOURS", "24"))

# ---------- Email (password reset) ----------
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "no-reply@albumai.local")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
# The print shop and delivery company's own inboxes — neither is a user of
# this app (no login), so every email they act on carries a signed link
# instead (see sign_order_action). One fixed address each, since this is
# a single-operator business with one print partner and one courier; if
# that ever changes, this would need to become per-order instead of a
# flat constant.
# The team's order inbox: told when the printer marks a book ready (test
# phase only) and when an order is delivered.
ORDERS_EMAIL = os.environ.get("ORDERS_EMAIL", "orders@everbook-album.com")
PRINTER_EMAIL = os.environ.get("PRINTER_EMAIL")
DELIVERY_EMAIL = os.environ.get("DELIVERY_EMAIL")

# ---------- Wakilni (the courier) ----------
# With a key and secret, a printed book marked ready by the printer becomes
# a Wakilni delivery and its status is followed from there (see
# services/wakilni.py); without them, the courier gets an email instead.
# https://api-dev.wakilni.com for testing, https://api.wakilni.com live.
WAKILNI_URL = (os.environ.get("WAKILNI_URL") or "https://api-dev.wakilni.com").rstrip("/")
WAKILNI_KEY = os.environ.get("WAKILNI_KEY")
WAKILNI_SECRET = os.environ.get("WAKILNI_SECRET")
# Where the courier picks the books up: the print shop.
# Its location id in Wakilni's portal (Locations), so Wakilni knows its
# full address; its GPS position as well (start bulk only takes these).
WAKILNI_PICKUP_LOCATION_ID = int(os.environ.get("WAKILNI_PICKUP_LOCATION_ID") or 1)
WAKILNI_PICKUP_AREA = os.environ.get("WAKILNI_PICKUP_AREA", "Furn el-Chebbak")
WAKILNI_PICKUP_DIRECTIONS = os.environ.get("WAKILNI_PICKUP_DIRECTIONS", "Bookstop, Gharios Center, next to SGBL")
WAKILNI_PICKUP_FLOOR = int(os.environ.get("WAKILNI_PICKUP_FLOOR") or 0)
WAKILNI_PICKUP_LATITUDE = float(os.environ.get("WAKILNI_PICKUP_LATITUDE") or 0) or None
WAKILNI_PICKUP_LONGITUDE = float(os.environ.get("WAKILNI_PICKUP_LONGITUDE") or 0) or None

# ---------- WhatsApp (Meta's Cloud API) ----------
# When a Wakilni delivery is created (the book is ready at the printer),
# Wakilni's team gets a WhatsApp message with Wakilni's order number, to
# come and pick it up (see services/whatsapp.py). Sent from Everbook's own
# WhatsApp Business number, with a message template approved by Meta.
# Without a token, a number id and recipients, nothing is sent.
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
# Wakilni's people, comma-separated, with the country code (961…).
WHATSAPP_PICKUP_TO = [n for n in (os.environ.get("WHATSAPP_PICKUP_TO") or "").replace(";", ",").split(",") if n.strip()]
# The template's name and language in Meta's WhatsApp Manager. Its text has
# two variables: {{1}} Wakilni's order number, {{2}} the number of albums.
WHATSAPP_PICKUP_TEMPLATE = os.environ.get("WHATSAPP_PICKUP_TEMPLATE", "wakilni_pickup")
# Bookstop's people, the same way: told on WhatsApp when an order is sent
# to print (the files stay in their email). Template variables: {{1}} the
# order number(s), {{2}} the number of albums.
WHATSAPP_PRINTER_TO = [n for n in (os.environ.get("WHATSAPP_PRINTER_TO") or "").replace(";", ",").split(",") if n.strip()]
WHATSAPP_PRINTER_TEMPLATE = os.environ.get("WHATSAPP_PRINTER_TEMPLATE", "bookstop_new_order")
WHATSAPP_TEMPLATE_LANGUAGE = os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
WHATSAPP_API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v23.0")

# ---------- OAuth (Google / Apple) ----------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID")  # Apple "Services ID"

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "album-photo")

# Websites allowed to call the API from a browser — see app/main.py.
CORS_ORIGINS = parse_cors_origins(os.environ.get("CORS_ORIGINS"), FRONTEND_URL)
CORS_ORIGIN_REGEX = os.environ.get("CORS_ORIGIN_REGEX") or None
