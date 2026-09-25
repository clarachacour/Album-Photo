"""Google Cloud Tasks: runs order PDF generation outside the order request.

Background work inside a Cloud Run request doesn't survive: once the
response is sent the instance loses its CPU (tried twice, the generation
went silent). A Cloud Tasks queue instead calls our own endpoint with an
ordinary request that has the CPU for its whole duration (up to 30
minutes), and retries it when it fails."""
import json
import logging

from app.config import BACKEND_URL, CLEANUP_SECRET, PDF_TASKS_QUEUE

logger = logging.getLogger(__name__)

TASKS_API = "https://cloudtasks.googleapis.com/v2"
# Longest a queue lets one call run (Cloud Tasks' maximum).
DISPATCH_DEADLINE_SECONDS = 1800


def pdf_tasks_enabled() -> bool:
    return bool(PDF_TASKS_QUEUE and CLEANUP_SECRET and BACKEND_URL)


def _session():
    # The Cloud Run service's own identity (it needs the "Cloud Tasks
    # Enqueuer" role on the queue).
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(credentials)


def enqueue_order_pdf(order_id: str) -> None:
    """Adds the order's PDF generation to the queue. Raises on failure."""
    task = {
        "httpRequest": {
            "httpMethod": "POST",
            "url": f"{BACKEND_URL}/api/internal/orders/{order_id}/generate-pdf",
            "headers": {"Content-Type": "application/json", "X-Cleanup-Secret": CLEANUP_SECRET},
            "body": "",
        },
        "dispatchDeadline": f"{DISPATCH_DEADLINE_SECONDS}s",
    }
    resp = _session().post(f"{TASKS_API}/{PDF_TASKS_QUEUE}/tasks", data=json.dumps({"task": task}), timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Cloud Tasks refused the task ({resp.status_code}): {resp.text[:300]}")
    logger.info(f"Commande {order_id} : génération du PDF mise en file d'attente")
