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

# Length limits on what people type: without them a 100,000-character
# name or a 2 MB contact message was stored (and emailed) as is.
Name = Annotated[str, Field(min_length=1, max_length=100)]
OptName = Annotated[Optional[str], Field(default=None, max_length=100)]
Phone = Annotated[str, Field(min_length=1, max_length=40)]
OptPhone = Annotated[Optional[str], Field(default=None, max_length=40)]
Line = Annotated[str, Field(min_length=1, max_length=200)]
OptLine = Annotated[Optional[str], Field(default=None, max_length=200)]
OptNote = Annotated[Optional[str], Field(default=None, max_length=500)]
Token = Annotated[str, Field(max_length=4096)]
Id = Annotated[str, Field(max_length=100)]
# Pages an album can have (tiers go up to 250; custom counts above that).
MAX_ALBUM_PAGES = 500


# ---------- Models ----------
class SignupInput(BaseModel):
    email: EmailStr
    password: NewPassword
    name: Name

class LoginInput(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(max_length=200)]

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
    name: OptName
    phone: OptPhone
    street: OptLine
    building: OptLine
    city: OptName
    additional_info: OptNote

class ChangePasswordInput(BaseModel):
    current_password: Annotated[str, Field(max_length=200)]
    new_password: NewPassword

class ContactInput(BaseModel):
    name: Name
    email: EmailStr
    subject: Line
    message: str = Field(min_length=1, max_length=5000)

class ShippingAddress(BaseModel):
    full_name: Name
    phone: Phone
    street: Line
    building: OptLine
    city: Name
    additional_info: OptNote

class OrderCreate(BaseModel):
    album_id: Id
    quantity: int = Field(default=1, ge=1, le=20)
    shipping_address: ShippingAddress

class AuthResponse(BaseModel):
    token: str
    user: UserOut

class ForgotPasswordInput(BaseModel):
    email: EmailStr

class ResetPasswordInput(BaseModel):
    token: Token
    new_password: NewPassword

class GoogleAuthInput(BaseModel):
    credential: Token  # ID token from Google Identity Services

class AppleAuthInput(BaseModel):
    id_token: Token
    name: OptName  # Apple only ever sends the name on first authorization

class AlbumCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=200)
    country: str = Field(default="", max_length=100)
    year: int = Field(default_factory=lambda: datetime.now().year, ge=1900, le=2200)
    cover_template_id: str = Field(default="default", max_length=100)
    cover: Optional[Dict[str, Any]] = None
    size: str = Field(default="A4", max_length=10)  # A4 or A5
    orientation: str = Field(default="portrait", max_length=20)  # portrait or landscape
    target_pages: int = Field(default=50, ge=1, le=MAX_ALBUM_PAGES)  # one of PAGE_TIERS, or any custom page count
    # The site's current UI language (see i18n.js on the frontend) at the
    # moment of creation — used only to pick which language the title
    # page's pre-filled hint text is written in (see make_title_page).
    # Never stored anywhere or used again after that; the person can still
    # freely edit or delete the hint afterward regardless of language.
    lang: str = Field(default="en", max_length=10)

class AlbumUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    country: Optional[str] = Field(default=None, max_length=100)
    year: Optional[int] = Field(default=None, ge=1900, le=2200)
    cover_template_id: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=10)
    orientation: Optional[str] = Field(default=None, max_length=20)
    target_pages: Optional[int] = Field(default=None, ge=1, le=MAX_ALBUM_PAGES)
    # Pages people add by hand can go past target_pages.
    pages: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=MAX_ALBUM_PAGES + 100)
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
    access_token: Token
    items: List[Dict[str, Any]] = Field(max_length=100)  # one batch of raw mediaItems from the Photos Picker API — the frontend now fetches the full selection itself and sends it here in small batches (same shape as regular multi-photo upload), instead of handing over a session_id and making the backend do everything (originals, potentially hundreds of them) inside a single background task. A background task only gets a fraction of its normal CPU once Cloud Run's request-based billing considers the request "done" — which made large imports far slower than an equivalent active request. Small batches processed as ordinary active requests never hit that throttling, exactly like regular device uploads already didn't.

class RepackPagesInput(BaseModel):
    target_pages: int = Field(gt=0, le=MAX_ALBUM_PAGES)
    keep_first_pages: int = Field(ge=0, default=0, le=MAX_ALBUM_PAGES)  # e.g. 40 — pages the person already hand-edited and doesn't want touched

class OrderFeedbackInput(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)

class OrderStatusUpdate(BaseModel):
    status: str = Field(max_length=40)
    tracking_number: OptLine
