import React from "react";
import { Link, useNavigate } from "react-router-dom";

export const isSignedIn = () => {
  try {
    return Boolean(localStorage.getItem("album_token") || localStorage.getItem("album_user"));
  } catch {
    return false;
  }
};

/** "Create my album": a real link (search engines, assistants and "open in
 * a new tab" see where it goes) to the sign-in page, which opens on creating
 * an account for a first visit. Someone already signed in goes to their
 * albums instead. The address is the same for everyone, so the page drawn at
 * build time matches the one in the browser. */
export function SignupLink({ children, onClick, ...props }) {
  const navigate = useNavigate();
  const go = (e) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (isSignedIn()) {
      e.preventDefault();
      navigate("/dashboard");
    }
  };
  return (
    <Link to="/auth" onClick={go} {...props}>
      {children}
    </Link>
  );
}
