import React from "react";
import { LAYOUT_PATTERNS, LAYOUT_GROUPS } from "@/lib/layoutPatterns";
import { X } from "lucide-react";

function LayoutThumb({ name }) {
  const { slots } = LAYOUT_PATTERNS[name];
  return (
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <rect x="0" y="0" width="100" height="100" fill="var(--paper)" />
      {slots.map((s, i) => (
        <rect
          key={i}
          x={s.x * 100}
          y={s.y * 100}
          width={s.w * 100}
          height={s.h * 100}
          fill="var(--editor-canvas)"
          stroke="var(--ink)"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}

/**
 * Lets the user replace a page's layout with an empty template (1 to 4
 * photo slots, several arrangements per count) — the resulting frames are
 * empty placeholders the user fills by dragging photos onto them, and each
 * frame can still be freely moved/resized afterward like any other.
 */
export default function LayoutPicker({ onChoose, onClose }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6" onClick={onClose}>
      <div
        className="bg-[color:var(--paper)] max-w-lg w-full p-6 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-serif-display text-2xl tracking-tight">Choose a layout</h3>
          <button onClick={onClose} className="text-[color:var(--muted)] hover:text-[color:var(--ink)]" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <p className="text-sm text-[color:var(--ink)]/70 mb-6">
          Your existing photos move into the new arrangement, and any extra slots the layout needs appear empty — drag your photos onto them, and you can still resize or move any frame afterward.
        </p>
        {LAYOUT_GROUPS.map((group) => (
          <div key={group.count} className="mb-6">
            <div className="eyebrow mb-3 text-[color:var(--muted)]">{group.count} photo{group.count > 1 ? "s" : ""}</div>
            <div className="grid grid-cols-2 gap-3">
              {group.patterns.map((name) => (
                <button
                  key={name}
                  onClick={() => onChoose(name)}
                  data-testid={`layout-option-${name}`}
                  className="border border-[color:var(--border-soft)] hover:border-[color:var(--coral)] transition-colors p-3 flex flex-col items-center gap-2"
                >
                  <div className="w-full aspect-[3/4] max-w-[110px]">
                    <LayoutThumb name={name} />
                  </div>
                  <span className="text-xs text-[color:var(--ink)]/70">{LAYOUT_PATTERNS[name].label}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}