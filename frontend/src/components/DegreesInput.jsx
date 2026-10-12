import React, { useState } from "react";
import { useTranslation } from "react-i18next";

// A typed angle, read as whole degrees within -180..180 ("-12,6" → -13);
// null while it isn't a number yet.
export function clampDegrees(text) {
  const trimmed = String(text).trim();
  if (trimmed === "" || trimmed === "-") return null;
  const n = Math.round(Number(trimmed.replace(",", ".")));
  if (!Number.isFinite(n)) return null;
  return Math.max(-180, Math.min(180, n));
}

/**
 * The exact rotation, typed in and applied as you type. While typing, the
 * field keeps what's typed (empty, "-"…) so any digit can be erased and
 * replaced — 0 included; it shows the real value again when left.
 * `dark`: for the black toolbars over a page.
 */
export function DegreesInput({ value, onChange, tid, dark = false }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(null);
  return (
    <label
      className={`flex items-center border ${
        dark
          ? "border-white/25 bg-white/10 focus-within:border-white/60"
          : "border-[color:var(--ink)]/20 bg-white focus-within:border-[color:var(--ink)]"
      }`}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      <input
        type="text"
        inputMode="numeric"
        data-testid={tid}
        aria-label={t("coverPanel.rotation")}
        value={draft ?? String(Math.round(value || 0))}
        onFocus={(e) => e.target.select()}
        onChange={(e) => {
          setDraft(e.target.value);
          const deg = clampDegrees(e.target.value);
          if (deg !== null) onChange(deg);
        }}
        onBlur={() => setDraft(null)}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          // Typing here never triggers the editor's shortcuts (Delete, Ctrl+Z…).
          e.stopPropagation();
        }}
        className={`w-10 py-1 pl-1.5 text-xs font-mono text-right bg-transparent focus:outline-none ${dark ? "text-[color:var(--paper)]" : ""}`}
      />
      <span className={`pr-1.5 text-xs font-mono ${dark ? "text-white/60" : "text-[color:var(--muted)]"}`}>°</span>
    </label>
  );
}
