import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { Package, LifeBuoy } from "lucide-react";

export default function AccountPage() {
  const { user, updateUser } = useAuth();
  const [form, setForm] = useState({
    name: user?.name || "",
    phone: user?.phone || "",
    address_line1: user?.address_line1 || "",
    city: user?.city || "",
    country: user?.country || "",
  });
  const [saving, setSaving] = useState(false);

  const [pwForm, setPwForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [changingPw, setChangingPw] = useState(false);

  const saveProfile = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.put("/auth/me", form);
      updateUser(data);
      toast.success("Profile updated");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update profile");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (e) => {
    e.preventDefault();
    if (pwForm.new_password !== pwForm.confirm) {
      toast.error("New passwords don't match");
      return;
    }
    setChangingPw(true);
    try {
      await api.put("/auth/password", {
        current_password: pwForm.current_password,
        new_password: pwForm.new_password,
      });
      toast.success("Password updated");
      setPwForm({ current_password: "", new_password: "", confirm: "" });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update password");
    } finally {
      setChangingPw(false);
    }
  };

  const inputClass =
    "w-full border border-[color:var(--ink)]/20 p-3 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[900px] mx-auto">
        <div className="mb-12">
          <div className="eyebrow mb-3">Account</div>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight">Your account</h1>
        </div>

        <div className="flex gap-4 mb-16">
          <Link
            to="/orders"
            className="inline-flex items-center gap-2 border border-[color:var(--ink)]/20 px-5 py-3 text-sm font-medium hover:border-[color:var(--ink)] transition-colors"
          >
            <Package size={15} /> My orders
          </Link>
          <Link
            to="/contact"
            className="inline-flex items-center gap-2 border border-[color:var(--ink)]/20 px-5 py-3 text-sm font-medium hover:border-[color:var(--ink)] transition-colors"
          >
            <LifeBuoy size={15} /> Contact support
          </Link>
        </div>

        <form onSubmit={saveProfile} className="mb-20">
          <div className="eyebrow mb-6">Profile & shipping details</div>
          <div className="grid md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="eyebrow block mb-2">Name</label>
              <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="eyebrow block mb-2">Email</label>
              <input className={inputClass + " opacity-60"} value={user?.email || ""} disabled />
            </div>
            <div>
              <label className="eyebrow block mb-2">Phone</label>
              <input className={inputClass} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
            <div>
              <label className="eyebrow block mb-2">Country</label>
              <input className={inputClass} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} />
            </div>
            <div className="md:col-span-2">
              <label className="eyebrow block mb-2">Address line</label>
              <input className={inputClass} value={form.address_line1} onChange={(e) => setForm({ ...form, address_line1: e.target.value })} />
            </div>
            <div>
              <label className="eyebrow block mb-2">City</label>
              <input className={inputClass} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
            </div>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </form>

        <form onSubmit={changePassword} className="border-t border-[color:var(--border-soft)] pt-12">
          <div className="eyebrow mb-6">Change password</div>
          <div className="grid md:grid-cols-3 gap-4 mb-4 max-w-2xl">
            <div>
              <label className="eyebrow block mb-2">Current password</label>
              <input
                type="password"
                className={inputClass}
                value={pwForm.current_password}
                onChange={(e) => setPwForm({ ...pwForm, current_password: e.target.value })}
              />
            </div>
            <div>
              <label className="eyebrow block mb-2">New password</label>
              <input
                type="password"
                className={inputClass}
                value={pwForm.new_password}
                onChange={(e) => setPwForm({ ...pwForm, new_password: e.target.value })}
              />
            </div>
            <div>
              <label className="eyebrow block mb-2">Confirm new password</label>
              <input
                type="password"
                className={inputClass}
                value={pwForm.confirm}
                onChange={(e) => setPwForm({ ...pwForm, confirm: e.target.value })}
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={changingPw}
            className="inline-flex items-center gap-2 border border-[color:var(--ink)] px-8 py-3 hover:bg-[color:var(--ink)] hover:text-[color:var(--paper)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-50"
          >
            {changingPw ? "Updating…" : "Update password"}
          </button>
        </form>
      </div>
    </main>
  );
}
