"""Rate limiter instance and the limits applied to sensitive endpoints."""
import os

from app.core.security import RateLimiter
from app.db import db

# ---------- Rate limiting ----------
# Counters live in MongoDB so the limits hold across every Cloud Run
# instance (see security.RateLimiter). Can be switched off with
# RATE_LIMIT_ENABLED=false, e.g. for an automated test run — never in prod.
rate_limiter = RateLimiter(
    db.rate_limits,
    enabled=os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off"),
)
# (limit, window in seconds). Per email *and* per IP: the email limit stops
# password guessing on one account even from many IPs; the IP limit stops
# one visitor from trying many accounts or spamming forms.
LOGIN_LIMIT_PER_EMAIL = (10, 15 * 60)
LOGIN_LIMIT_PER_IP = (30, 15 * 60)
FORGOT_PASSWORD_LIMIT_PER_EMAIL = (3, 60 * 60)
FORGOT_PASSWORD_LIMIT_PER_IP = (10, 60 * 60)
CONTACT_LIMIT_PER_IP = (5, 60 * 60)
