// The order number everyone uses — the customer, the admin, the printer and
// the courier: "EB-" and the order id's first 8 characters, in capitals
// (same as the backend's app/core/order_number.py).
export function orderNumber(order) {
  return `EB-${String(order?.id || "").slice(0, 8).toUpperCase()}`;
}
