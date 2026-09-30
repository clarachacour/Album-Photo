"""A slow mail server must not freeze the site for everyone else."""
import asyncio
import time
import uuid

import httpx


def test_a_slow_email_does_not_block_other_requests(app, monkeypatch):
    from app.services import email

    # Email configured, but the mail server takes 1.5 s to answer.
    monkeypatch.setattr(email, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email, "SMTP_USER", "u")
    monkeypatch.setattr(email, "SMTP_PASSWORD", "p")

    class SlowSMTP:
        def __init__(self, *a, **k):
            time.sleep(1.5)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, *a):
            pass

    monkeypatch.setattr(email.smtplib, "SMTP", SlowSMTP)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            signup = asyncio.create_task(client.post("/api/auth/signup", json={"email": f"{uuid.uuid4().hex[:8]}@example.com", "password": "secret123", "name": "Slow"}))
            # Meanwhile another visitor keeps using the site: note the
            # longest they ever had to wait for an answer.
            longest = 0.0
            while not signup.done():
                start = time.monotonic()
                await asyncio.sleep(0.05)
                health = await client.get("/api/")
                assert health.status_code == 200
                longest = max(longest, time.monotonic() - start - 0.05)
            return (await signup).status_code, longest

    signup_status, longest_wait = asyncio.run(scenario())
    assert signup_status == 200
    assert longest_wait < 0.5, f"another visitor waited {longest_wait:.1f} s behind the email"
