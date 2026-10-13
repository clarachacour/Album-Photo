"""The order number everyone uses: the customer, the admin, the printer and
the courier (Wakilni's waybill) — "EB-" and the first 8 characters of the
order's id, in capitals (order 5f4c0509-… → EB-5F4C0509)."""


def order_number(order: dict) -> str:
    return f"EB-{order['id'][:8].upper()}"
