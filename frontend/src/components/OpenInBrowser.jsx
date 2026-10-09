import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ExternalLink, X } from "lucide-react";
import { copyText, externalBrowserUrl, inAppBrowser } from "@/lib/inAppBrowser";

/**
 * "android" / "ios" in an app's own browser (Instagram, Messenger…), else
 * null. Read after the first render: the pages are also made on the server
 * (prerender), where there is no browser to look at.
 */
export function useInAppBrowser() {
  const [platform, setPlatform] = useState(null);
  useEffect(() => setPlatform(inAppBrowser()), []);
  return platform;
}

function OpenButtons({ platform, className = "" }) {
  const { t } = useTranslation();
  const copy = async () => {
    const ok = await copyText(window.location.href);
    if (ok) toast.success(t("inApp.copied"));
    else toast.error(t("inApp.copyFailed"));
  };
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      <a
        href={externalBrowserUrl(window.location.href, platform)}
        className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-4 py-2 text-xs font-semibold tracking-widest uppercase"
      >
        <ExternalLink className="w-3.5 h-3.5" />
        {t(platform === "ios" ? "inApp.openSafari" : "inApp.openChrome")}
      </a>
      <button
        type="button"
        onClick={copy}
        className="border border-[color:var(--ink)]/40 px-4 py-2 text-xs font-semibold tracking-widest uppercase"
      >
        {t("inApp.copyLink")}
      </button>
    </div>
  );
}

const DISMISSED = "everbook_in_app_banner_closed";

/** Bar at the bottom of the site, in an app's own browser. */
export function InAppBrowserBanner() {
  const { t } = useTranslation();
  const platform = useInAppBrowser();
  const [closed, setClosed] = useState(() => {
    try {
      return typeof sessionStorage !== "undefined" && sessionStorage.getItem(DISMISSED) === "1";
    } catch {
      return false;
    }
  });
  if (!platform || closed) return null;
  const close = () => {
    setClosed(true);
    try {
      sessionStorage.setItem(DISMISSED, "1");
    } catch {
      /* closed for this page only */
    }
  };
  return (
    <div data-testid="in-app-banner" className="fixed bottom-0 inset-x-0 z-50 bg-[color:var(--paper)] border-t border-[color:var(--ink)]/15 shadow-[0_-6px_24px_rgba(0,0,0,0.08)] px-4 py-3">
      <div className="max-w-xl mx-auto flex items-start gap-3">
        <div className="flex-1">
          <p className="text-sm text-[color:var(--ink)]">{t("inApp.banner")}</p>
          <p className="text-xs text-[color:var(--muted)] mt-1">{t(platform === "ios" ? "inApp.howIos" : "inApp.howAndroid")}</p>
          <OpenButtons platform={platform} className="mt-3" />
        </div>
        <button type="button" onClick={close} aria-label={t("inApp.close")} className="p-1 text-[color:var(--muted)]">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

/** In place of "Continue with Google" on the sign-in page. */
export function InAppSignInNotice({ platform }) {
  const { t } = useTranslation();
  return (
    <div data-testid="in-app-signin-notice" className="border border-[color:var(--ink)]/15 bg-white/60 p-4">
      <p className="text-sm text-[color:var(--ink)]">{t("inApp.signIn")}</p>
      <p className="text-xs text-[color:var(--muted)] mt-1">{t(platform === "ios" ? "inApp.howIos" : "inApp.howAndroid")}</p>
      <OpenButtons platform={platform} className="mt-3" />
      <p className="text-xs text-[color:var(--muted)] mt-3">{t("inApp.orEmail")}</p>
    </div>
  );
}
