import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import { i18nReady } from "@/lib/i18n";
import App from "@/App";
import { initMonitoring } from "@/lib/monitoring";
import { initAnalytics } from "@/lib/analytics";

initMonitoring();
initAnalytics();

// The page drawn at build time (public pages, see prerender.jsx) stays on
// screen while the visitor's language downloads; the app then takes it over
// as it is (hydrate) instead of drawing it again, so it doesn't flash and
// its photo isn't loaded twice. Where it differs (a signed-in visitor's
// menu…), React redraws that part. The app's other pages start empty.
const start = () => {
  const container = document.getElementById("root");
  if (container.hasChildNodes()) {
    ReactDOM.hydrateRoot(container, <App />, {
      // A page that differs from the one drawn at build time: React draws it
      // again, nothing to report.
      onRecoverableError: () => {},
    });
  } else {
    ReactDOM.createRoot(container).render(<App />);
  }
};

// The texts couldn't be downloaded, even after a few tries (a bad
// connection, or a tab opened before a new version of the site):
// - a page drawn at build time stays as it is — readable, its links work;
// - otherwise the page is reloaded once, to get the site's current files;
//   if that was already done, the app starts anyway (rather than nothing).
const RELOAD_FLAG = "everbook_texts_reload";
const textsFailed = () => {
  const container = document.getElementById("root");
  if (container.hasChildNodes()) return;
  let reloaded = true;
  try {
    reloaded = sessionStorage.getItem(RELOAD_FLAG) === "1";
    if (!reloaded) sessionStorage.setItem(RELOAD_FLAG, "1");
  } catch {
    /* storage unavailable: no reload, to avoid a loop */
  }
  if (!reloaded) window.location.reload();
  else start();
};

i18nReady.then(start, textsFailed);
