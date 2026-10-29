"""Online payment — not set up yet.

The one place a checkout asks to be paid (today: gift cards; later the
whole cart). For now it accepts every payment as made, without charging
anything, so the rest of the flow (gift card activated, emails…) works
as it will. When the payment provider is set up, only this function
changes: charge `amount_cents`, return "paid" or "failed" (and keep the
provider's reference in the result)."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Whish Pay and card payment: not offered yet. Until then printed albums
# are paid cash on delivery (the courier collects the total), and what
# can't be — the PDF and gift cards, with nothing delivered — is shown as
# "coming soon" and can't be ordered (routers/cart.py, routers/orders.py).
ONLINE_PAYMENT = False
NEEDS_ONLINE_PAYMENT = "Coming soon: the PDF and gift cards will be available with Whish Pay and card payment"


async def collect_payment(user: dict, checkout_id: str, amount_cents: int, description: str) -> dict:
    """Returns {"status": "paid" | "failed", "provider", "reference",
    "amount_cents", "at"}."""
    logger.info(f"Panier {checkout_id} : paiement de {amount_cents / 100:.2f} USD accepté sans encaissement (paiement en ligne pas encore en place) — {description}")
    return {
        "status": "paid",
        "provider": None,  # no payment provider yet
        "reference": None,
        "amount_cents": amount_cents,
        "at": datetime.now(timezone.utc).isoformat(),
    }
