"""Online payment: Whish Pay (see services/whish.py and routers/payments.py).

On once the Whish keys are set on the server (config.WHISH_*). Until then
printed albums are paid cash on delivery (the courier collects the total),
and what can't be — the PDF and gift cards, with nothing delivered — is
shown as "coming soon" and can't be ordered (routers/cart.py)."""
from app.services import whish

ONLINE_PAYMENT = whish.enabled()
NEEDS_ONLINE_PAYMENT = "Coming soon: the PDF and gift cards will be available with Whish Pay"
# Whish takes at least this much (USD 1.00).
MIN_ONLINE_CENTS = 100
