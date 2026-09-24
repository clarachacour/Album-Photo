import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, ArrowLeft } from "lucide-react";

export default function OrderFeedback() {
  const { id } = useParams();
  const { t } = useTranslation();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/orders/${id}`);
        setOrder(data);
        if (data.feedback?.comment) {
          setComment(data.feedback.comment);
          setSent(true);
        }
      } catch {
        toast.error(t("orderFeedback.loadError"));
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      await api.post(`/orders/${id}/feedback`, { comment });
      setSent(true);
      toast.success(t("orderFeedback.sentToast"));
    } catch {
      toast.error(t("orderFeedback.sendError"));
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12 flex items-center justify-center">
        <Loader2 className="animate-spin text-[color:var(--muted)]" size={28} />
      </main>
    );
  }
  if (!order) return null;

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[700px] mx-auto">
        <Link to={`/orders/${id}`} className="inline-flex items-center gap-2 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-8 transition-colors">
          <ArrowLeft size={14} /> {t("orderDetail.back")}
        </Link>

        <div className="mb-10">
          <div className="eyebrow mb-3">{order.album_title}</div>
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight">{t("orderFeedback.title")}</h1>
          <p className="text-[color:var(--ink)]/70 mt-3">{t("orderFeedback.subtitle")}</p>
        </div>

        {sent ? (
          <div className="border border-[color:var(--border-soft)] p-8">
            <p className="font-serif-display text-2xl tracking-tight mb-2">{t("orderFeedback.thanks")}</p>
            <p className="text-sm text-[color:var(--ink)]/70 whitespace-pre-wrap">{comment}</p>
          </div>
        ) : (
          <form onSubmit={submit}>
            <textarea
              rows={6}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={t("orderFeedback.placeholder")}
              required
              className="w-full border border-[color:var(--ink)]/20 p-4 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none resize-none mb-6"
            />
            <button
              type="submit"
              disabled={sending}
              className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-50"
            >
              {sending && <Loader2 size={14} className="animate-spin" />}
              {sending ? t("orderFeedback.sending") : t("orderFeedback.submit")}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
