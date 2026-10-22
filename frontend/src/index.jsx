import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import { i18nReady } from "@/lib/i18n";
import App from "@/App";
import { initMonitoring } from "@/lib/monitoring";

initMonitoring();

// The page drawn at build time (public pages, see prerender.jsx) stays on
// screen while the visitor's language downloads; the app then takes it over
// as it is (hydrate) instead of drawing it again, so it doesn't flash and
// its photo isn't loaded twice. Where it differs (a signed-in visitor's
// menu…), React redraws that part. The app's other pages start empty.
i18nReady.finally(() => {
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
});
