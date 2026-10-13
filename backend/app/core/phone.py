"""Lebanese phone numbers (delivery is in Lebanon only): what the courier
calls. Accepted with or without the country code (+961 / 00961 / 961), with
spaces, dashes, dots or brackets; stored as the 8-digit national number.

- mobiles: 03 / 70 / 71 / 76 / 78 / 79 / 81 + 6 digits (03 is written 3
  after +961: +961 3 123 456)
- landlines: 01, 04, 05, 06, 07, 08, 09 + 6 digits (+961 1 234 567)
"""
import re

MOBILE_PREFIXES = ("03", "70", "71", "76", "78", "79", "81")
LANDLINE_PREFIXES = ("01", "04", "05", "06", "07", "08", "09")


def normalize_lebanese_phone(value: str) -> str:
    """The 8-digit national number (e.g. "70123456", "03123456"), or
    ValueError if it isn't a Lebanese number."""
    digits = re.sub(r"[\s\-\.\(\)/]", "", str(value or ""))
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        raise ValueError("Please enter a Lebanese phone number (e.g. 70 123 456 or 03 123 456)")
    international = False
    for code in ("00961", "961"):
        if digits.startswith(code) and len(digits) - len(code) in (7, 8):
            digits = digits[len(code):]
            international = True
            break
    # After +961 the 0 is dropped (+961 3 123 456 = 03 123 456); without
    # it, only an 03 mobile is commonly written without its 0.
    if len(digits) == 7 and (international or digits.startswith("3")):
        digits = "0" + digits
    if len(digits) == 8 and digits[:2] in MOBILE_PREFIXES + LANDLINE_PREFIXES:
        return digits
    raise ValueError("Please enter a Lebanese phone number (e.g. 70 123 456 or 03 123 456)")


def optional_lebanese_phone(value):
    """The same for an optional field: empty stays empty."""
    if value is None or not str(value).strip():
        return None
    return normalize_lebanese_phone(value)
