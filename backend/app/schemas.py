"""Pydantic models: the shape of request bodies and responses."""
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _fits_bcrypt(password: str) -> str:
    # bcrypt only reads the first 72 bytes and the library refuses longer
    # input (the signup used to crash with a 500).
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 characters")
    return password


# Any password a person sets (signup, change, reset).
NewPassword = Annotated[str, Field(min_length=6), AfterValidator(_fits_bcrypt)]


# ---------- Models ----------
class SignupInput(BaseModel):
    email: EmailStr
    password: NewPassword
    name: str = Field(min_length=1)

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    phone: Optional[str] = None
    street: Optional[str] = None
    building: Optional[str] = None
    city: Optional[str] = None
    additional_info: Optional[str] = None
    # Computed from ADMIN_EMAIL, never stored — lets the frontend show/hide
    # the admin nav link without hardcoding the admin's address a second
    # time in frontend code (which would just be one more place for it to
    # drift out of sync with the real check, which always lives server-side
    # in require_admin regardless of what this flag says).
    is_admin: bool = False
    # True for every account that either doesn't need verification at all
    # (Google/Apple sign-in, or any account created before this feature
    # existed) or has already clicked its link — only a brand-new classic
    # signup starts out False. The frontend uses this to decide whether to
    # show the "check your inbox" screen instead of the dashboard; the
    # actual enforcement lives server-side in get_current_user regardless
    # of what the frontend does with this flag.
    email_verified: bool = True

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    building: Optional[str] = None
    city: Optional[str] = None
    additional_info: Optional[str] = None

class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: NewPassword

class ContactInput(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    subject: str = Field(min_length=1)
    message: str = Field(min_length=1)

class ShippingAddress(BaseModel):
    full_name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    street: str = Field(min_length=1)
    building: Optional[str] = None
    city: str = Field(min_length=1)
    additional_info: Optional[str] = None

class OrderCreate(BaseModel):
    album_id: str
    quantity: int = Field(default=1, ge=1, le=20)
    shipping_address: ShippingAddress

class AuthResponse(BaseModel):
    token: str
    user: UserOut

class ForgotPasswordInput(BaseModel):
    email: EmailStr

class ResetPasswordInput(BaseModel):
    token: str
    new_password: NewPassword

class GoogleAuthInput(BaseModel):
    credential: str  # ID token from Google Identity Services

class AppleAuthInput(BaseModel):
    id_token: str
    name: Optional[str] = None  # Apple only ever sends the name on first authorization

class AlbumCreate(BaseModel):
    title: str = "Untitled"
    country: str = ""
    year: int = Field(default_factory=lambda: datetime.now().year)
    cover_template_id: str = "default"
    cover: Optional[Dict[str, Any]] = None
    size: str = "A4"  # A3, A4 or A5
    orientation: str = "portrait"  # portrait or landscape
    target_pages: int = 50  # one of PAGE_TIERS, or any custom page count
    # The site's current UI language (see i18n.js on the frontend) at the
    # moment of creation — used only to pick which language the title
    # page's pre-filled hint text is written in (see make_title_page).
    # Never stored anywhere or used again after that; the person can still
    # freely edit or delete the hint afterward regardless of language.
    lang: str = "en"

class AlbumUpdate(BaseModel):
    title: Optional[str] = None
    country: Optional[str] = None
    year: Optional[int] = None
    cover_template_id: Optional[str] = None
    size: Optional[str] = None
    orientation: Optional[str] = None
    target_pages: Optional[int] = None
    pages: Optional[List[Dict[str, Any]]] = None
    cover: Optional[Dict[str, Any]] = None
    # No status or cover_image_path: only the server sets them. A client
    # able to write cover_image_path could point it at another customer's
    # file and read it through the cover image endpoint. Unknown fields in
    # the request are ignored.

class MobileUploadSessionOut(BaseModel):
    token: str
    upload_url: str
    expires_at: str

class MobileUploadStatusInput(BaseModel):
    uploading: bool

# ---------- Google Photos import (Photos Picker API) ----------
class GooglePhotosImportInput(BaseModel):
    access_token: str
    items: List[Dict[str, Any]]  # one batch of raw mediaItems from the Photos Picker API — the frontend now fetches the full selection itself and sends it here in small batches (same shape as regular multi-photo upload), instead of handing over a session_id and making the backend do everything (originals, potentially hundreds of them) inside a single background task. A background task only gets a fraction of its normal CPU once Cloud Run's request-based billing considers the request "done" — which made large imports far slower than an equivalent active request. Small batches processed as ordinary active requests never hit that throttling, exactly like regular device uploads already didn't.

class RepackPagesInput(BaseModel):
    target_pages: int = Field(gt=0)
    keep_first_pages: int = Field(ge=0, default=0)  # e.g. 40 — pages the person already hand-edited and doesn't want touched

class OrderFeedbackInput(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)

class OrderStatusUpdate(BaseModel):
    status: str
    tracking_number: Optional[str] = None
