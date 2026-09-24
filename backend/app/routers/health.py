"""Health check."""

from fastapi import APIRouter

router = APIRouter()


# ---------- Health ----------
@router.get("/")
async def root():
    return {"status": "ok", "service": "Album AI Studio"}
