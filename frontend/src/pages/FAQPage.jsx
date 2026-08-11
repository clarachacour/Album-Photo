import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";

const FAQS = [
  {
    q: "How long does it take to receive my album?",
    a: "Once your order is placed, we prepare and print your album, then ship it to you. You can follow every step from your Orders page.",
  },
  {
    q: "What formats are available?",
    a: "A5, A4 and A3, in either portrait or landscape orientation. You choose the format when you create your album, and can see it reflected live in the editor.",
  },
  {
    q: "Can I edit my album after placing an order?",
    a: "Once an order is placed, your album is sent into production shortly after, so further edits won't be reflected in that particular order. If you need a change, contact us as soon as possible and we'll do our best to help.",
  },
  {
    q: "How does the AI photo selection work?",
    a: "When you import a large batch of photos, we automatically detect near-duplicates and bursts, keep the sharpest shot from each, and use AI to help group and describe the best of what's left — so you spend less time sorting and more time enjoying the result.",
  },
  {
    q: "Can I order more than one copy?",
    a: "Yes — you can choose a quantity when placing your order, for example to give copies as gifts.",
  },
  {
    q: "What if something arrives damaged or wrong?",
    a: "Reach out through our Contact page with your order number and we'll sort it out.",
  },
];

export default function FAQPage() {
  const [openIdx, setOpenIdx] = useState(null);

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[800px] mx-auto">
        <div className="mb-16">
          <div className="eyebrow mb-3">Support</div>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight mb-4">Frequently asked questions</h1>
          <p className="text-sm text-[color:var(--muted)]">
            Can't find what you're looking for?{" "}
            <Link to="/contact" className="underline text-[color:var(--ink)]">
              Get in touch
            </Link>
            .
          </p>
        </div>

        <div className="divide-y divide-[color:var(--border-soft)] border-t border-b border-[color:var(--border-soft)]">
          {FAQS.map((item, i) => (
            <div key={i}>
              <button
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                className="w-full flex items-center justify-between gap-4 py-6 text-left"
                data-testid={`faq-question-${i}`}
              >
                <span className="font-serif-display text-lg md:text-xl tracking-tight">{item.q}</span>
                <ChevronDown
                  size={18}
                  className={`shrink-0 transition-transform ${openIdx === i ? "rotate-180" : ""}`}
                />
              </button>
              {openIdx === i && (
                <p className="text-sm text-[color:var(--ink)]/70 leading-relaxed pb-6 pr-8">{item.a}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}