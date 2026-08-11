import React, { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function ContactPage() {
  const { user } = useAuth();
  const [form, setForm] = useState({ name: user?.name || "", email: user?.email || "", subject: "", message: "" });
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      await api.post("/contact", form);
      setSent(true);
      toast.success("Message sent");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to send your message");
    } finally {
      setSending(false);
    }
  };

  const inputClass =
    "w-full border border-[color:var(--ink)]/20 p-3 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[700px] mx-auto">
        <div className="mb-12">
          <div className="eyebrow mb-3">Support</div>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight">Contact us</h1>
        </div>

        {sent ? (
          <div className="border border-[color:var(--border-soft)] p-10 text-center">
            <p className="font-serif-display text-2xl tracking-tight mb-2">Thanks for reaching out</p>
            <p className="text-sm text-[color:var(--muted)]">We'll get back to you as soon as we can.</p>
          </div>
        ) : (
          <form onSubmit={submit}>
            <div className="grid md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="eyebrow block mb-2">Name</label>
                <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
              </div>
              <div>
                <label className="eyebrow block mb-2">Email</label>
                <input type="email" className={inputClass} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Subject</label>
                <input className={inputClass} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Message</label>
                <textarea
                  rows={6}
                  className={inputClass + " resize-none"}
                  value={form.message}
                  onChange={(e) => setForm({ ...form, message: e.target.value })}
                  required
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={sending}
              className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-60"
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : null}
              {sending ? "Sending…" : "Send message"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}