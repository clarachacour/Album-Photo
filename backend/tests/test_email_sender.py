"""The customer sees "Everbook" as the name of the sender."""
from app.services import email


def test_the_sender_is_named_everbook(monkeypatch):
    monkeypatch.setattr(email, "SMTP_FROM", "orders@everbook-album.com")
    assert email.sender() == ("Everbook <orders@everbook-album.com>", "orders@everbook-album.com")
    # A name already written in the setting is kept.
    monkeypatch.setattr(email, "SMTP_FROM", "Everbook Album <orders@everbook-album.com>")
    assert email.sender() == ("Everbook Album <orders@everbook-album.com>", "orders@everbook-album.com")


def test_the_email_sent_carries_the_name(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def sendmail(self, frm, to, raw):
            sent.update(frm=frm, raw=raw)

    monkeypatch.setattr(email, "SMTP_FROM", "orders@everbook-album.com")
    for name, value in (("SMTP_HOST", "smtp.example.com"), ("SMTP_USER", "u"), ("SMTP_PASSWORD", "p")):
        monkeypatch.setattr(email, name, value)
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    email.send_email("client@example.com", "Votre commande", "Bonjour")
    assert sent["frm"] == "orders@everbook-album.com"
    assert "From: Everbook <orders@everbook-album.com>" in sent["raw"]
