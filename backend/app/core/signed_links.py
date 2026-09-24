"""Signed links for the printer and delivery emails (no login needed)."""
import base64
import hashlib
import hmac

from app.config import JWT_SECRET


# The printer and delivery company aren't users of this app — they act on
# a specific order purely by clicking a link in an email, with no login.
# Each link is signed (HMAC, using the same secret as user auth tokens,
# but a completely different, non-JWT format — never decodable as a user
# session) so the action it grants (downloading one order's PDF, marking
# one order ready) can't be guessed or reused for a different order.
def sign_order_action(order_id: str, action: str) -> str:
    msg = f"{order_id}:{action}".encode()
    sig = hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")

def verify_order_action(order_id: str, action: str, token: str) -> bool:
    if not token:
        return False
    expected = sign_order_action(order_id, action)
    return hmac.compare_digest(expected, token)
