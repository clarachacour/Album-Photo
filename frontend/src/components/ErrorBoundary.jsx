import React from "react";
import { withTranslation } from "react-i18next";
import { reportError } from "@/lib/monitoring";

/**
 * Catches a crash while a page renders and shows a way out instead of a
 * blank screen; the error is reported to Sentry when it's configured.
 * `resetKey` (the current address) clears the error when the person
 * navigates elsewhere.
 */
class ErrorBoundaryInner extends React.Component {
  state = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error) {
    return { error };
  }

  static getDerivedStateFromProps(props, state) {
    if (props.resetKey !== state.resetKey) return { error: null, resetKey: props.resetKey };
    return null;
  }

  componentDidCatch(error, info) {
    console.error(error);
    reportError(error, { componentStack: info?.componentStack });
  }

  render() {
    const { t, renderFallback } = this.props;
    if (!this.state.error) return this.props.children;
    if (renderFallback) return renderFallback(this.state.error);
    return (
      <main className="min-h-[70vh] flex items-center justify-center p-8 bg-[color:var(--paper)]" data-testid="error-boundary">
        <div className="w-full max-w-md text-center">
          <h1 className="font-serif-display text-4xl tracking-tight mb-3">{t("errorBoundary.title")}</h1>
          <p className="text-[color:var(--ink)]/70 mb-8">{t("errorBoundary.body")}</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center justify-center bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors"
            >
              <span className="text-sm font-semibold tracking-widest uppercase">{t("errorBoundary.reload")}</span>
            </button>
            <a
              href="/dashboard"
              className="inline-flex items-center justify-center border border-[color:var(--ink)]/30 px-8 py-3 hover:border-[color:var(--ink)] transition-colors"
            >
              <span className="text-sm font-semibold tracking-widest uppercase">{t("errorBoundary.myAlbums")}</span>
            </a>
          </div>
        </div>
      </main>
    );
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryInner);
