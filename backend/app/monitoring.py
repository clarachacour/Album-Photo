"""Error monitoring with Sentry — only when SENTRY_DSN is set (Cloud Run
environment variable). Without it, nothing is sent anywhere."""
import logging
import os

logger = logging.getLogger(__name__)


def _scrub(event, hint):
    # Tokens travel in query strings (?auth=, ?token=): never send them.
    request = event.get("request") or {}
    if request.get("query_string"):
        request["query_string"] = "[removed]"
    if isinstance(request.get("url"), str):
        request["url"] = request["url"].split("?")[0]
    return event


def send_test_error():
    """Sends a deliberate error to Sentry (admin "Test Sentry" button).
    Returns the event id, or None when Sentry isn't configured."""
    if not os.environ.get("SENTRY_DSN"):
        return None
    import sentry_sdk

    try:
        raise RuntimeError("Sentry test from the admin page (backend) — safe to ignore")
    except RuntimeError as e:
        event_id = sentry_sdk.capture_exception(e)
    sentry_sdk.flush(timeout=5)
    return event_id


def init_monitoring():
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        # Errors only: no performance tracing.
        traces_sample_rate=0,
        # No IP addresses, cookies or login headers.
        send_default_pii=False,
        before_send=_scrub,
    )
    logger.info("Sentry error monitoring enabled")
    return True
