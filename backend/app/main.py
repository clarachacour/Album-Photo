"""Entry point: builds the FastAPI app and plugs every router into it.

Run locally from backend/ with:  uvicorn app.main:app --reload
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    # The default Windows event loop (Selector) can't spawn subprocesses,
    # which is exactly what Playwright needs to launch the browser for PDF
    # export — without this, it fails with NotImplementedError. Must be set
    # before uvicorn/FastAPI create their event loop, so this needs to run
    # at import time, before anything else touches asyncio.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGIN_REGEX, CORS_ORIGINS
from app.core.rate_limit import rate_limiter
from app.db import client, db
from app.routers import (
    admin,
    albums,
    auth,
    contact,
    covers,
    health,
    internal,
    mobile_upload,
    orders,
    photos,
)
from app.db_indexes import ensure_indexes
from app.services.storage import init_storage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_storage()
    await ensure_indexes(db)
    await rate_limiter.ensure_indexes()
    logger.info("Startup complete")
    yield
    # Shutdown
    client.close()


app = FastAPI(title="Album AI Studio API", lifespan=lifespan)

# Every route lives under /api. Order matters when two paths could match the
# same URL, so keep this list in the same order as before the split.
api_router = APIRouter(prefix="/api")
for module in (auth, contact, albums, photos, mobile_upload, covers, orders, admin, internal, health):
    api_router.include_router(module.router)
app.include_router(api_router)

# Only the websites listed here may call the API from a browser (never
# "*"). CORS_ORIGINS is a comma-separated list; FRONTEND_URL is always
# included. CORS_ORIGIN_REGEX optionally allows a pattern of URLs on top —
# keep it strict: a loose *.vercel.app pattern would match strangers' sites.
logger.info("CORS allowed origins: %s%s", CORS_ORIGINS, f" + regex {CORS_ORIGIN_REGEX}" if CORS_ORIGIN_REGEX else "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    # The frontend authenticates with an "Authorization: Bearer" header and
    # never with cookies, so browsers don't need to send credentials.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
