import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// The customer's cart, kept on their account by the server (routers/cart.py):
// albums added one by one — printed, as a PDF, or both — then ordered all at
// once. Shared here so the header's cart icon and the pages agree.
const CartContext = createContext({ cart: null, count: 0 });

export function CartProvider({ children }) {
  const { user } = useAuth();
  const [cart, setCart] = useState(null);

  const refresh = useCallback(async () => {
    if (!user) return setCart(null);
    try {
      const { data } = await api.get("/cart");
      setCart(data);
      return data;
    } catch {
      return null;
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Each call answers with the whole cart, kept as is.
  const add = async (albumId, kind, quantity = 1) => {
    const { data } = await api.post("/cart/items", { album_id: albumId, kind, quantity });
    setCart(data);
    return data;
  };
  // A gift card: { size, page_tier, recipient_name, message, from_name, lang }.
  const addGift = async (gift) => {
    const { data } = await api.post("/cart/gifts", gift);
    setCart(data);
    return data;
  };
  const setQuantity = async (itemId, quantity) => {
    const { data } = await api.patch(`/cart/items/${itemId}`, { quantity });
    setCart(data);
    return data;
  };
  const remove = async (itemId) => {
    const { data } = await api.delete(`/cart/items/${itemId}`);
    setCart(data);
    return data;
  };

  return (
    <CartContext.Provider value={{ cart, count: cart?.count || 0, refresh, add, addGift, setQuantity, remove, setCart }}>
      {children}
    </CartContext.Provider>
  );
}

export const useCart = () => useContext(CartContext);
