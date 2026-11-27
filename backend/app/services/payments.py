"""How orders are paid: online, with Whish Pay (services/whish.py) or a card
(services/cybersource.py), each on once its keys are set on the server.

Cash on delivery is switched off (CASH_ON_DELIVERY): everything is paid
online. Orders placed on delivery before that keep their cash collection by
the courier (services/wakilni.py). Without any online payment on, nothing
paid can be ordered."""
from app.services import cybersource, whish

ONLINE_PAYMENT = whish.enabled()
# Card payment (Cybersource through areeba): on once its keys are set.
CARD_PAYMENT = cybersource.enabled()


# Paying the courier on delivery (printed albums only). Off: every order is
# paid online (Whish Pay or card) — unless there's nothing left to pay.
CASH_ON_DELIVERY = False


def any_online() -> bool:
    """Something online is on (Whish Pay or card): gift cards and PDFs can
    be ordered."""
    return ONLINE_PAYMENT or CARD_PAYMENT
NEEDS_ONLINE_PAYMENT = "Online payment is unavailable right now — please try again in a moment"
# Whish takes at least this much (USD 1.00).
MIN_ONLINE_CENTS = 100
