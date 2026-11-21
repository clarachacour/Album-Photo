import React, { useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

// Lower case, without accents: "Achrafieh" matches "achrafiéh".
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

/** The areas matching what's typed: those starting with it first, then
 *  those containing it (all of them when nothing is typed). */
export function matchAreas(areas, query) {
  const q = fold(query);
  if (!q) return areas;
  const starts = [];
  const contains = [];
  for (const a of areas) {
    const f = fold(a);
    if (f.startsWith(q)) starts.push(a);
    else if (f.includes(q)) contains.push(a);
  }
  return [...starts, ...contains];
}

/**
 * The delivery area: a text field with the courier's areas listed under it,
 * filtered as the customer types — instead of a <datalist>, which Safari on
 * iPhone shows as a few suggestions over the keyboard, not as a list.
 */
export default function AreaPicker({ areas, value, onChange, className, placeholder, testId }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const listRef = useRef(null);
  // Typing filters; a value picked from the list shows the whole list again
  // when the field is reopened (to change it).
  const [query, setQuery] = useState("");
  const shown = useMemo(() => matchAreas(areas, query), [areas, query]);

  const pick = (area) => {
    onChange(area);
    setQuery("");
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(shown.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter" && open && active >= 0 && shown[active]) {
      e.preventDefault();
      pick(shown[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <input
        className={className}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setQuery(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        // After a tap on the list (which comes after the blur on phones).
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        data-testid={testId}
      />
      {open && areas.length > 0 && (
        <ul
          id={listId}
          ref={listRef}
          role="listbox"
          className="absolute z-30 left-0 right-0 mt-1 max-h-64 overflow-y-auto overscroll-contain bg-white border border-ink/20 shadow-lg text-sm"
          data-testid="area-options"
        >
          {shown.length === 0 ? (
            <li className="px-3 py-3 text-[color:var(--muted)]">{t("checkout.areaNoMatch")}</li>
          ) : (
            shown.map((a, i) => (
              <li
                key={a}
                role="option"
                aria-selected={i === active}
                // mousedown (not click): picked before the field's blur.
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(a);
                }}
                className={`px-3 py-3 cursor-pointer border-b border-ink/5 last:border-0 ${i === active ? "bg-[color:var(--paper)]" : "hover:bg-[color:var(--paper)]"}`}
              >
                {a}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
