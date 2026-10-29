"""Promo codes in the admin: create, switch off or on, change the last day,
see how many times each was used (services/promo_codes.py)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.auth import get_current_user, require_admin
from app.db import db
from app.schemas import PromoCodeInput, PromoCodeUpdate
from app.services import promo_codes

router = APIRouter()


async def _with_uses(promo: dict) -> dict:
    return {**promo, "uses": await promo_codes.uses(promo["code"])}


@router.get("/admin/promo-codes")
async def list_promo_codes(user: dict = Depends(get_current_user)):
    require_admin(user)
    codes = await db.promo_codes.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [await _with_uses(c) for c in codes]


@router.post("/admin/promo-codes")
async def create_promo_code(data: PromoCodeInput, user: dict = Depends(get_current_user)):
    require_admin(user)
    code = promo_codes.normalize(data.code)
    if not promo_codes.CODE_PATTERN.match(code):
        raise HTTPException(status_code=400, detail="A code is 3 to 30 letters, digits or dashes")
    promo = {"code": code, "percent": data.percent, "ends_on": data.ends_on or None, "active": True,
             "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        await db.promo_codes.insert_one(promo)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="This code already exists")
    promo.pop("_id", None)
    return await _with_uses(promo)


@router.patch("/admin/promo-codes/{code}")
async def update_promo_code(code: str, data: PromoCodeUpdate, user: dict = Depends(get_current_user)):
    require_admin(user)
    changes = data.model_dump(exclude_unset=True)
    if "ends_on" in changes:
        changes["ends_on"] = changes["ends_on"] or None
    promo = await db.promo_codes.find_one_and_update(
        {"code": promo_codes.normalize(code)}, {"$set": changes}, projection={"_id": 0}, return_document=True
    )
    if not promo:
        raise HTTPException(status_code=404, detail="No such code")
    return await _with_uses(promo)
