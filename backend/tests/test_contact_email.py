def test_contact_message_can_be_answered(client, monkeypatch):
    """The team's copy of a contact message shows the sender's address in
    full and has it as Reply-To, so "Reply" answers the customer."""
    from app.services import email as email_module

    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, sender, to, message):
            sent.append(message)

    monkeypatch.setenv("SUPPORT_EMAIL", "team@everbook.test")
    for name, value in (("SMTP_HOST", "smtp.test"), ("SMTP_USER", "u"), ("SMTP_PASSWORD", "p")):
        monkeypatch.setattr(email_module, name, value)
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)

    res = client.post("/api/contact", json={"name": "Rita Haddad", "email": "rita@example.com", "subject": "Mon album", "message": "Bonjour"})
    assert res.status_code == 200
    assert len(sent) == 1
    import email as email_lib

    msg = email_lib.message_from_string(sent[0])
    assert msg["Reply-To"] == "rita@example.com"
    assert msg["To"] == "team@everbook.test"
    plain = next(part for part in msg.walk() if part.get_content_type() == "text/plain").get_payload(decode=True).decode()
    assert "Email: rita@example.com" in plain
