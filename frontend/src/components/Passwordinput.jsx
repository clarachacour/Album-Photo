import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff } from "lucide-react";

// A drop-in replacement for <input type="password" ...> that adds a
// show/hide toggle — every prop except `type` (fixed by this component,
// toggled internally) passes straight through, so it works with any
// existing className/value/onChange without each page having to
// duplicate the toggle logic and icon styling itself.
export default function PasswordInput({ className = "", ...props }) {
  const [visible, setVisible] = useState(false);
  const { t } = useTranslation();
  return (
    <div className="relative w-full">
      <input {...props} type={visible ? "text" : "password"} className={`${className} pr-10`} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        // tabIndex={-1}: this is a convenience toggle, not a form field —
        // keeping it out of the tab order means Tab from the password
        // field goes straight to the next real field, not this button.
        tabIndex={-1}
        aria-label={visible ? t("common.hidePassword") : t("common.showPassword")}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
