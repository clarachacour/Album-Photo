import pytest

from app.core.phone import normalize_lebanese_phone, optional_lebanese_phone


@pytest.mark.parametrize("typed, stored", [
    ("70 123 456", "70123456"),
    ("+961 70 123 456", "70123456"),
    ("00961-71-123456", "71123456"),
    ("03 123 456", "03123456"),
    ("+961 3 123 456", "03123456"),
    ("961 81 234 567", "81234567"),
    ("(01) 234-567", "01234567"),
    ("+9611234567", "01234567"),
    ("3 123 456", "03123456"),
])
def test_accepts_lebanese_numbers(typed, stored):
    assert normalize_lebanese_phone(typed) == stored


@pytest.mark.parametrize("typed", ["", "12345", "+33 6 12 34 56 78", "72 123 456", "70 123 45", "abc", "+961 70 123 4567"])
def test_refuses_anything_else(typed):
    with pytest.raises(ValueError):
        normalize_lebanese_phone(typed)


def test_an_optional_phone_can_stay_empty():
    assert optional_lebanese_phone("") is None and optional_lebanese_phone(None) is None
