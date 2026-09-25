// Error monitoring with Sentry — only when REACT_APP_SENTRY_DSN is set
// (Vercel → Settings → Environment Variables). Loaded on demand so the
// site doesn't carry Sentry's code when it isn't configured.
const DSN = import.meta.env.REACT_APP_SENTRY_DSN;
let sentry = null;

export async function initMonitoring() {
  if (!DSN) return;
  try {
    const Sentry = await import("@sentry/react");
    Sentry.init({
      dsn: DSN,
      environment: import.meta.env.REACT_APP_SENTRY_ENVIRONMENT || import.meta.env.MODE,
      // Errors only: no performance tracing or session replay.
      tracesSampleRate: 0,
      // The print page's address carries a login token.
      beforeSend(event) {
        if (event.request?.url) event.request.url = event.request.url.split("?")[0];
        return event;
      },
    });
    sentry = Sentry;
  } catch (e) {
    console.warn("Sentry could not start", e);
  }
}

export function reportError(error, extra) {
  if (sentry) sentry.captureException(error, extra ? { extra } : undefined);
}
