"""Every email the app sends (customers, printer, delivery)."""
import html
import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr

from app.config import (
    ADMIN_EMAIL,
    BACKEND_URL,
    DELIVERY_EMAIL,
    DRAFT_ALBUM_RETENTION_DAYS,
    FRONTEND_URL,
    ORDERS_EMAIL,
    PRINTER_EMAIL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)
from app.core.order_number import order_number
from app.core.signed_links import sign_order_action

logger = logging.getLogger(__name__)


def _h(value) -> str:
    """Text typed by a customer (name, album title, address…), made safe to
    put in an HTML email: shown as text, never read as a link or markup."""
    return html.escape(str(value if value is not None else ""))


def send_email(to_email: str, subject: str, body: str, html_body: str = None, reply_to: str = None, attachments: list = None):
    """attachments: [(file name, bytes, "application/pdf")…], only given when there are some."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        # No email provider configured — log it so it's usable in local/dev
        # testing without silently failing. Set SMTP_HOST/SMTP_USER/
        # SMTP_PASSWORD to send real emails.
        logger.warning(f"[DEV] SMTP non configuré — email non envoyé à {to_email} : {subject}\n{body}")
        return
    try:
        if html_body:
            # multipart/alternative: mail clients that render HTML show
            # html_body (needed for an actual clickable button); anything
            # that can't falls back to the plain-text part instead of
            # showing broken markup.
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
        else:
            msg = MIMEText(body)
        if attachments:
            # The text (and its HTML version) first, then the files.
            mixed = MIMEMultipart("mixed")
            mixed.attach(msg)
            for filename, data, mime in attachments:
                part = MIMEApplication(data, _subtype=mime.split("/", 1)[1])
                part.add_header("Content-Disposition", "attachment", filename=filename)
                mixed.attach(part)
            msg = mixed
        # Album titles and contact subjects end up here: a line break would
        # start a new header line.
        msg["Subject"] = " ".join(str(subject).split())
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        # Standard headers Python doesn't add on its own: spam filters
        # (Outlook especially) mark down an email without them.
        msg["Date"] = formatdate(localtime=False)
        sender_domain = parseaddr(SMTP_FROM)[1].rpartition("@")[2] or None
        msg["Message-ID"] = make_msgid(domain=sender_domain)
        if reply_to:
            # "Reply" in the mail app then writes to this address (the
            # customer, for the contact form) instead of to the site.
            msg["Reply-To"] = " ".join(str(reply_to).split())
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
    except Exception as e:
        logger.error(f"Échec de l'envoi de l'email à {to_email} : {e}")

# Everbook's on-site color tokens (frontend/src/index.css :root) — kept as
# the single source of truth for every branded email built with
# _email_wrapper below, rather than each send_*_email guessing its own
# approximate hex values that would drift from the site over time.
_EMAIL_INK = "#1A1A17"
_EMAIL_PAPER = "#F9F8F6"
_EMAIL_CANVAS = "#EAE9E4"
_EMAIL_CORAL = "#E56B55"
_EMAIL_MUTED = "#73716A"
_EMAIL_BORDER = "#E2DFD8"
# Georgia is the closest widely-installed serif to the site's actual
# display font (Cormorant Garamond / Baloo 2, both web fonts email clients
# won't load) — email clients render almost nothing else reliably, so
# this is the honest ceiling for matching the site's look here, not a
# placeholder waiting to be swapped for the real thing.
_EMAIL_SERIF = "Georgia, 'Times New Roman', serif"
_EMAIL_SANS = "Helvetica, Arial, sans-serif"

def _email_wrapper(preheader: str, title: str, body_html: str, cta_label: str = None, cta_url: str = None) -> str:
    """Wraps any email's content in Everbook's branded shell — the same
    wordmark, paper background, ink text, and coral call-to-action button
    used across every automated email (welcome, verification, password,
    order status, printer/delivery notices, admin alerts). A single
    shared wrapper means every email stays visually consistent and only
    has to change in one place if the site's own colors ever do, instead
    of each send_*_email function hand-rolling its own HTML (as
    send_printer_order_email used to, before this existed).

    There's no actual logo image file anywhere in this codebase — the
    site's own header (TopNav.jsx) doesn't render one either, just this
    same styled text wordmark, so recreating that exactly here (rather
    than inventing a graphical logo that doesn't exist on the site
    itself) is what "matching the site" actually means.

    body_html and preheader are HTML: every customer-typed value in them
    goes through _h() first."""
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px auto 0;">
          <tr><td style="background-color:{_EMAIL_CORAL}; border-radius:2px;">
            <a href="{cta_url}" style="display:inline-block; padding:14px 32px; color:{_EMAIL_PAPER}; text-decoration:none; font-family:{_EMAIL_SANS}; font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase;">{cta_label}</a>
          </td></tr>
        </table>
        """
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background-color:{_EMAIL_CANVAS};">
  <span style="display:none; max-height:0; overflow:hidden; font-size:1px; color:{_EMAIL_CANVAS};">{preheader}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_EMAIL_CANVAS};">
    <tr><td align="center" style="padding: 40px 20px;">
      <table role="presentation" width="100%" style="max-width:520px; background-color:{_EMAIL_PAPER}; border:1px solid {_EMAIL_BORDER};">
        <tr><td style="padding: 36px 40px 24px; text-align:center; border-bottom:1px solid {_EMAIL_BORDER};">
          <span style="font-family:{_EMAIL_SERIF}; font-size:26px; font-weight:500; color:{_EMAIL_INK}; letter-spacing:0.5px;">Everbook</span>
        </td></tr>
        <tr><td style="padding: 40px;">
          <h1 style="font-family:{_EMAIL_SERIF}; font-size:23px; font-weight:500; color:{_EMAIL_INK}; margin:0 0 18px; line-height:1.3;">{title}</h1>
          <div style="font-family:{_EMAIL_SANS}; font-size:15px; line-height:1.65; color:{_EMAIL_INK};">
            {body_html}
          </div>
          {cta_html}
        </td></tr>
        <tr><td style="padding: 22px 40px; border-top:1px solid {_EMAIL_BORDER}; text-align:center;">
          <p style="font-family:{_EMAIL_SANS}; font-size:12px; color:{_EMAIL_MUTED}; margin:0;">Everbook · <a href="{FRONTEND_URL}" style="color:{_EMAIL_MUTED};">{FRONTEND_URL.replace("https://", "").replace("http://", "")}</a></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

def send_welcome_email(to_email: str, name: str):
    subject = "Welcome to Everbook"
    body = (
        f"Hi {name or ''},\n\n"
        f"Welcome to Everbook — you're all set to start turning your photos into a printed book.\n\n"
        f"Upload your photos, let us help lay them out, and order a copy whenever you're ready.\n\n"
        f"{FRONTEND_URL}"
    )
    html_body = _email_wrapper(
        preheader="You're all set to start turning your photos into a printed book.",
        title="Welcome to Everbook.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>You're all set to start turning your photos into a printed book. "
            f"Upload your photos, let us help lay them out, and order a copy whenever you're ready.</p>"
        ),
        cta_label="Get started",
        cta_url=FRONTEND_URL,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_verification_email(to_email: str, name: str, verify_token: str, welcome: bool = False):
    """Sent right at signup (welcome=True — see signup) and again whenever
    resend_verification_email is called (welcome=False, a plain reminder
    rather than a second "welcome") — never for Google/Apple accounts,
    whose provider has already confirmed the address (see
    upsert_oauth_user). The link goes straight to a backend endpoint
    (verify_email) rather than a frontend page, since there's nothing for
    the person to fill in or decide — one click is the whole interaction,
    the same shape as the printer/delivery action links (sign_order_action)
    elsewhere in this file, just without needing HMAC signing since the
    token itself is the single-use credential, stored and cleared server-
    side rather than reconstructed from a signature.

    welcome=True folds the account's very first email into this one
    single message instead of sending a separate "Welcome to Everbook"
    right alongside it — two emails at once meant the welcome one's own
    "Get started" link took someone straight past the confirmation step
    entirely (the site still blocks them once there, but arriving at a
    page that looks ready before confirming anything is confusing on its
    own). One email, one action, matches what a click from an inbox
    should actually lead to."""
    verify_link = f"{BACKEND_URL}/api/auth/verify-email?token={verify_token}"
    subject = "Welcome to Everbook — confirm your email" if welcome else "Confirm your email address"
    intro = (
        "Welcome to Everbook — you're almost set up. Please confirm this is your email address to finish creating your account and start turning your photos into a printed book."
        if welcome
        else "Please confirm this is your email address to finish setting up your account."
    )
    body = (
        f"Hi {name or ''},\n\n"
        f"{intro}\n\n"
        f"{verify_link}\n\n"
        f"If you didn't create an Everbook account, you can safely ignore this email."
    )
    html_body = _email_wrapper(
        preheader=intro,
        title="Welcome to Everbook." if welcome else "Confirm your email address.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>{intro}</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">If you didn't create an Everbook account, "
            f"you can safely ignore this email.</p>"
        ),
        cta_label="Confirm email address",
        cta_url=verify_link,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_pdf_generation_failed_email(order: dict, error: str):
    """Sent to the admin (reusing ADMIN_EMAIL — the same address that
    already has visibility into every order via the admin endpoints, so
    this doesn't introduce a second address to keep in sync) the moment a
    PDF generation attempt fails outright. Previously a failure only ever
    showed up in Cloud Run's own logs or the admin orders page — nothing
    proactively said "this needs attention", which is exactly what let
    the Western Australia album's stuck generation go unnoticed for as
    long as it did. Best-effort: if ADMIN_EMAIL isn't set, send_email's
    own SMTP-not-configured branch already logs a warning, so this never
    raises on top of the failure it's reporting."""
    if not ADMIN_EMAIL:
        return
    admin_url = f"{FRONTEND_URL}/admin/orders"
    subject = f"PDF generation failed — order {order_number(order)} ({order.get('album_title', 'Album')})"
    body = (
        f"PDF generation failed for an order and needs attention.\n\n"
        f"Album: {order.get('album_title', 'Album')}\n"
        f"Order ID: {order['id']}\n"
        f"Size/pages: {order.get('size')} · {order.get('orientation')}\n\n"
        f"Error: {error}\n\n"
        f"Regenerate or investigate here:\n{admin_url}"
    )
    html_body = _email_wrapper(
        preheader=f"PDF generation failed for order {order_number(order)}",
        title="PDF generation failed.",
        body_html=(
            f"<p>An order's PDF generation attempt failed and needs attention.</p>"
            f"<p><strong>Album:</strong> {_h(order.get('album_title', 'Album'))}<br>"
            f"<strong>Order ID:</strong> {order['id']}<br>"
            f"<strong>Format:</strong> {order.get('size')} · {order.get('orientation')}</p>"
            f"<p><strong>Error:</strong><br><span style=\"font-family:monospace; font-size:13px;\">{_h(error)}</span></p>"
        ),
        cta_label="Open admin orders",
        cta_url=admin_url,
    )
    send_email(ADMIN_EMAIL, subject, body, html_body=html_body)

def send_password_reset_email(to_email: str, name: str, reset_link: str):
    subject = "Reset your password"
    body = (
        f"Hi {name or ''},\n\n"
        f"Click the link below to reset your password (valid for 1 hour):\n{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    html_body = _email_wrapper(
        preheader="Click below to reset your Everbook password.",
        title="Reset your password.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Click the button below to reset your password. This link is valid for 1 hour.</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">If you didn't request this, "
            f"you can safely ignore this email.</p>"
        ),
        cta_label="Reset password",
        cta_url=reset_link,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_account_deleted_email(to_email: str, name: str):
    """Confirms an account deletion, so the owner knows it happened (and
    can reach us if it wasn't them)."""
    subject = "Your Everbook account was deleted"
    body = (
        f"Hi {name or ''},\n\n"
        f"Your Everbook account has been deleted, along with your albums and photos.\n\n"
        f"If you didn't ask for this, please contact us right away."
    )
    html_body = _email_wrapper(
        preheader="Your Everbook account and photos have been deleted.",
        title="Your account was deleted.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Your Everbook account has been deleted, along with your albums and photos.</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">If you didn't ask for this, please contact us right away.</p>"
        ),
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_password_changed_email(to_email: str, name: str):
    """A simple security notice, sent after a password change goes through
    successfully — via the "I know my current password" flow (change_password)
    or the "I forgot it" one (reset_password) alike, so either path leaves
    the same trace in the account owner's inbox. Never blocks or reverses
    the change itself if sending fails — this is a notification, not a
    confirmation step the change waits on. Deliberately doesn't link
    anywhere or ask the person to click anything: if this wasn't them, the
    account may already be compromised, and a suspicious link is exactly
    what a real phishing follow-up would look like."""
    subject = "Your Everbook password was changed"
    body = (
        f"Hi {name or ''},\n\n"
        f"This is a confirmation that your Everbook account password was just changed.\n\n"
        f"If this was you, no action is needed. If you didn't make this change, "
        f"please contact us right away so we can help secure your account."
    )
    html_body = _email_wrapper(
        preheader="Your Everbook account password was just changed.",
        title="Your password was changed.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>This is a confirmation that your Everbook account password was just changed.</p>"
            f"<p>If this was you, no action is needed. If you didn't make this change, "
            f"please contact us right away so we can help secure your account.</p>"
        ),
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_confirmation_email(to_email: str, name: str, order: dict):
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    total = order.get("total_price_cents", 0) / 100
    if order.get("kind") == "digital":
        return _send_digital_order_confirmation_email(to_email, name, order, order_url, total)
    subject = "Your Everbook order is confirmed"
    body = (
        f"Hi {name or ''},\n\n"
        f"Thanks for your order! We've received it and will start preparing your book.\n\n"
        + (f"Your album is free. Only the delivery, {total:.2f} {order.get('currency', 'usd').upper()}, is to be paid in cash to the courier.\n"
           if not order.get("unit_price_cents") else
           f"Order total: {total:.2f} {order.get('currency', 'usd').upper()} (delivery included), to be paid in cash to the courier.\n")
        +
        f"Quantity: {order.get('quantity', 1)}\n\n"
        f"You can follow its status here:\n{order_url}\n\n"
        f"We'll email you again once it ships."
    )
    html_body = _email_wrapper(
        preheader="Thanks for your order! We've received it and will start preparing your book.",
        title="Your order is confirmed.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Thanks for your order! We've received it and will start preparing your book.</p>"
            + (f"<p>Your album is free. Only the delivery, <strong>{total:.2f} {order.get('currency', 'usd').upper()}</strong>, is to be paid in cash to the courier.<br>"
               if not order.get("unit_price_cents") else
               f"<p><strong>Order total:</strong> {total:.2f} {order.get('currency', 'usd').upper()} (delivery included), to be paid in cash to the courier.<br>")
            +
            f"<strong>Quantity:</strong> {order.get('quantity', 1)}</p>"
            f"<p>We'll email you again once it ships.</p>"
        ),
        cta_label="Track your order",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_checkout_confirmation_email(to_email: str, name: str, orders: list):
    """One email for everything ordered together from the cart: each album
    and version, the total, how it's paid and what happens next."""
    currency = (orders[0].get("currency") or "usd").upper()
    prints = [o for o in orders if o.get("kind") != "digital"]
    digitals = [o for o in orders if o.get("kind") == "digital"]
    cash = sum(int(o.get("total_price_cents") or 0) for o in prints) / 100
    subject = f"Your Everbook order is confirmed — {len(orders)} items"
    orders_url = f"{FRONTEND_URL}/orders"

    def line(o):
        what = "PDF to download" if o.get("kind") == "digital" else f"printed album × {o.get('quantity', 1)}"
        return f"{o.get('album_title', 'Album')} — {what} ({order_number(o)})"

    notes = []
    if prints:
        notes.append(
            f"Your printed albums are delivered together, in one package. Online payment isn't set up yet: "
            f"the total, {cash:.2f} {currency} (delivery included), is paid in cash to the courier."
        )
    if digitals:
        notes.append(
            "Online payment isn't set up yet, so there's nothing to pay for your PDF for now: "
            "we'll email you the moment it's ready to download, in a few minutes."
        )
    body = (
        f"Hi {name or ''},\n\n"
        f"Thanks for your order! We've received it and are starting on it:\n\n"
        + "\n".join(f"- {line(o)}" for o in orders)
        + "\n\n" + "\n\n".join(notes)
        + f"\n\nYou can follow each of them here:\n{orders_url}"
    )
    html_body = _email_wrapper(
        preheader="Thanks for your order! We've received it and are starting on it.",
        title="Your order is confirmed.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Thanks for your order! We've received it and are starting on it:</p>"
            "<ul>" + "".join(f"<li>{_h(line(o))}</li>" for o in orders) + "</ul>"
            + "".join(f"<p>{_h(n)}</p>" for n in notes)
        ),
        cta_label="Track your orders",
        cta_url=orders_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_gift_cards_email(to_email: str, name: str, cards: list, pdfs: list):
    """To the buyer: their gift card(s) as PDF, to print or send on, with
    the code(s) written in the email too."""
    fr = (cards[0].get("lang") == "fr")
    many = len(cards) > 1
    page_url = f"{FRONTEND_URL}/orders"
    if fr:
        subject = "Vos cartes cadeaux Everbook" if many else "Votre carte cadeau Everbook"
        intro = (
            "Merci ! Voici vos cartes cadeaux, en PDF : imprimez-les ou envoyez-les telles quelles."
            if many else
            "Merci ! Voici votre carte cadeau, en PDF : imprimez-la ou envoyez-la telle quelle."
        )
        how = f"La personne qui la reçoit saisit le code sur {FRONTEND_URL}/gift et crée son album. Valable 12 mois."
        line = lambda c: f"{c['code']} — album {c['size']} de {c['page_tier']} pages, pour {c.get('recipient_name') or '…'}"  # noqa: E731
        again = "Vous les retrouvez aussi dans « Mes commandes »."
        cta = "Mes commandes"
    else:
        subject = "Your Everbook gift cards" if many else "Your Everbook gift card"
        intro = (
            "Thank you! Here are your gift cards, as PDFs: print them or send them on as they are."
            if many else
            "Thank you! Here's your gift card, as a PDF: print it or send it on as it is."
        )
        how = f"Whoever gets it enters the code on {FRONTEND_URL}/gift and creates their album. Valid for 12 months."
        line = lambda c: f"{c['code']} — {c['page_tier']}-page {c['size']} album, for {c.get('recipient_name') or '…'}"  # noqa: E731
        again = "You'll also find them in \"My orders\"."
        cta = "My orders"
    hello = f"{'Bonjour' if fr else 'Hi'} {name or ''},"
    body = f"{hello}\n\n{intro}\n\n" + "".join(f"- {line(c)}\n" for c in cards) + f"\n{how}\n\n{again}\n{page_url}"
    html_body = _email_wrapper(
        preheader=intro,
        title=subject + ".",
        body_html=(
            f"<p>{_h(hello)}</p><p>{_h(intro)}</p>"
            + "<ul>" + "".join(f"<li>{_h(line(c))}</li>" for c in cards) + "</ul>"
            + f"<p>{_h(how)}</p><p>{_h(again)}</p>"
        ),
        cta_label=cta,
        cta_url=page_url,
    )
    send_email(to_email, subject, body, html_body=html_body, attachments=pdfs)

def _send_digital_order_confirmation_email(to_email: str, name: str, order: dict, order_url: str, total: float):
    subject = "Your Everbook digital album is ordered"
    free = total == 0
    # Online payment isn't set up yet: the PDF is handed over at once either way.
    intro = (
        "Thanks for your order! Your digital album is free: it will be ready to download as a PDF in a few minutes."
        if free else
        "Thanks for your order! Online payment isn't set up yet, so there's nothing to pay for now: your album will be ready to download as a PDF in a few minutes."
    )
    body = (
        f"Hi {name or ''},\n\n"
        f"{intro}\n\n"
        f"You can follow your order here:\n{order_url}\n\n"
        f"We'll email you again the moment your PDF is ready."
    )
    html_body = _email_wrapper(
        preheader=intro,
        title="Your digital album is ordered.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>{intro}</p>"
            f"<p>We'll email you again the moment your PDF is ready.</p>"
        ),
        cta_label="View your order",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_digital_album_ready_email(to_email: str, name: str, order: dict):
    """Sent once a digital album is paid and its PDF made (see
    deliver_digital_if_ready): the download is on the order's page."""
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    title = order.get("album_title", "Your album")
    subject = f"Your Everbook album is ready to download — {title}"
    intro = f"Your album \"{title}\" is ready! You can download it as a PDF from your order, as many times as you like."
    body = (
        f"Hi {name or ''},\n\n"
        f"{intro}\n\n"
        f"Download it here:\n{order_url}\n\n"
        f"Thanks for choosing Everbook."
    )
    html_body = _email_wrapper(
        preheader=intro,
        title="Your album is ready to download.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Your album <strong>\u201c{_h(title)}\u201d</strong> is ready! You can download it as a PDF from your order, as many times as you like.</p>"
            f"<p>Thanks for choosing Everbook.</p>"
        ),
        cta_label="Download my album",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_in_production_email(to_email: str, name: str, order: dict, group: list = None):
    """To the customer: their book has gone to the printer — or, for albums
    sent to the printer together (`group`, see services/print_groups.py),
    all of them: one email for the order."""
    group = group or [order]
    many = len(group) > 1
    order_url = f"{FRONTEND_URL}/orders" if many else f"{FRONTEND_URL}/orders/{order['id']}"
    number = order_number(order)
    titles = [f"{o.get('album_title', 'Album')} ({order_number(o)})" for o in group]
    if many:
        subject = f"Your {len(group)} Everbook albums are being printed"
        news = f"Your {len(group)} albums have gone to the printer:"
        plain_news = news + "\n" + "".join(f"- {t}\n" for t in titles)
        html_news = f"<p>{news}</p><ul>" + "".join(f"<li>{_h(t)}</li>" for t in titles) + "</ul>"
        then = "Printing takes about 3 days, then they're handed to the courier together, in one package — we'll email you when they're on their way."
    else:
        subject = f"Your Everbook album is being printed ({number})"
        plain_news = f"Your album \"{order.get('album_title', 'Album')}\" has gone to the printer (order {number}).\n"
        html_news = f"<p>Your album <strong>{_h(order.get('album_title', 'Album'))}</strong> has gone to the printer (order {number}).</p>"
        then = "Printing takes about 3 days, then it's handed to the courier — we'll email you when it's on its way."
    body = (
        f"Hi {name or ''},\n\n"
        f"{plain_news}"
        f"{then}\n\n"
        f"Follow {'them' if many else 'your order'} here:\n{order_url}"
    )
    html_body = _email_wrapper(
        preheader="Your albums have gone to the printer." if many else "Your album has gone to the printer.",
        title="Your albums are being printed." if many else "Your album is being printed.",
        body_html=f"<p>Hi {_h(name or '')},</p>{html_news}<p>{then}</p>",
        cta_label="Follow your orders" if many else "Follow your order",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_shipped_email(to_email: str, name: str, order: dict, group: list = None):
    """The book is on its way — or, for albums delivered together (`group`,
    see services/print_groups.py), all of them: one email for the package."""
    group = group or [order]
    many = len(group) > 1
    order_url = f"{FRONTEND_URL}/orders" if many else f"{FRONTEND_URL}/orders/{order['id']}"
    tracking = order.get("tracking_number")
    # The courier's own tracking page, when the delivery is a Wakilni one.
    tracking_url = (order.get("delivery") or {}).get("tracking_url")
    subject = f"Your {len(group)} Everbook albums are on their way" if many else "Your Everbook order is on its way"
    news = (
        f"Good news — your {len(group)} books have shipped, together in one package!"
        if many else
        "Good news — your book has shipped!"
    )
    titles = [f"{o.get('album_title', 'Album')} ({order_number(o)})" for o in group]
    body = (
        f"Hi {name or ''},\n\n"
        f"{news}\n\n"
        + ("".join(f"- {t}\n" for t in titles) + "\n" if many else "")
        + (f"Tracking number: {tracking}\n\n" if tracking else "")
        + (f"Follow the courier here:\n{tracking_url}\n\n" if tracking_url else "")
        + f"You can follow {'them' if many else 'its status'} here:\n{order_url}"
    )
    html_body = _email_wrapper(
        preheader=news,
        title="Your order has shipped.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>{news}</p>"
            + ("<ul>" + "".join(f"<li>{_h(t)}</li>" for t in titles) + "</ul>" if many else "")
            + (f"<p><strong>Tracking number:</strong> {_h(tracking)}</p>" if tracking else "")
            + (f'<p><a href="{_h(tracking_url)}">Follow the courier</a></p>' if tracking_url else "")
        ),
        cta_label="Track your orders" if many else "Track your order",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_delivered_feedback_email(to_email: str, name: str, order: dict, group: list = None):
    """Delivered: we ask how it turned out — for albums delivered together
    (`group`), one email with a feedback link per album."""
    group = group or [order]
    many = len(group) > 1
    feedback_url = f"{FRONTEND_URL}/orders/{order['id']}/feedback"
    contact_url = f"{FRONTEND_URL}/contact"
    subject = "How did your Everbook albums turn out?" if many else "How did your Everbook turn out?"
    arrived = (
        f"Your {len(group)} books should have arrived by now — we hope you love them!"
        if many else
        "Your book should have arrived by now — we hope you love it!"
    )
    links = [(o.get("album_title", "Album"), f"{FRONTEND_URL}/orders/{o['id']}/feedback") for o in group]
    body = (
        f"Hi {name or ''},\n\n"
        f"{arrived}\n\n"
        + (
            "We'd love to hear what you thought of each one:\n" + "".join(f"- {t}: {u}\n" for t, u in links) + "\n"
            if many else
            f"We'd love to hear what you thought:\n{feedback_url}\n\n"
        )
        + f"If anything wasn't right, contact us instead:\n{contact_url}\n\n"
        f"Thank you for printing with Everbook."
    )
    html_body = _email_wrapper(
        preheader=arrived,
        title="How did your books turn out?" if many else "How did your book turn out?",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>{arrived}</p>"
            + (
                "<p>We'd love to hear what you thought of each one:</p><ul>"
                + "".join(f'<li><a href="{_h(u)}">{_h(t)}</a></li>' for t, u in links)
                + "</ul>"
                if many else
                "<p>We'd love to hear what you thought.</p>"
            )
            + f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">If anything wasn't right, "
            f"<a href=\"{contact_url}\" style=\"color:{_EMAIL_MUTED};\">contact us</a> instead — "
            f"we'll get back to you directly.</p>"
        ),
        cta_label="Share your feedback",
        cta_url=feedback_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_unfinished_album_reminder_email(to_email: str, name: str, album: dict):
    album_url = f"{FRONTEND_URL}/editor/{album['id']}"
    subject = f"Finish your Everbook album — {album.get('title', 'your album')}"
    body = (
        f"Hi {name or ''},\n\n"
        f"You started \"{album.get('title', 'an album')}\" but haven't finished it yet.\n\n"
        f"Pick up right where you left off:\n{album_url}\n\n"
        f"It only takes a few minutes to finish laying it out and order your printed copy."
    )
    html_body = _email_wrapper(
        preheader=f"You started \"{_h(album.get('title', 'an album'))}\" but haven't finished it yet.",
        title="Finish your album.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>You started \"{_h(album.get('title', 'an album'))}\" but haven't finished it yet.</p>"
            f"<p>It only takes a few minutes to finish laying it out and order your printed copy.</p>"
        ),
        cta_label="Pick up where you left off",
        cta_url=album_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_album_expiring_soon_email(to_email: str, name: str, album: dict, days_left: int):
    album_url = f"{FRONTEND_URL}/editor/{album['id']}"
    subject = f"\"{album.get('title', 'Your album')}\" will be deleted in {days_left} days"
    body = (
        f"Hi {name or ''},\n\n"
        f"\"{album.get('title', 'Your album')}\" hasn't been touched in a while, and unfinished albums are "
        f"automatically removed after {DRAFT_ALBUM_RETENTION_DAYS} days to free up space.\n\n"
        f"It'll be deleted in {days_left} days unless you open it again before then:\n{album_url}\n\n"
        f"If you're not planning to finish it, no action is needed."
    )
    html_body = _email_wrapper(
        preheader=f"\"{_h(album.get('title', 'Your album'))}\" will be deleted in {days_left} days unless you open it again.",
        title="Your album will be deleted soon.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>\"{_h(album.get('title', 'Your album'))}\" hasn't been touched in a while, and unfinished albums "
            f"are automatically removed after {DRAFT_ALBUM_RETENTION_DAYS} days to free up space.</p>"
            f"<p>It'll be deleted in {days_left} day{'s' if days_left != 1 else ''} unless you open it again before then. "
            f"If you're not planning to finish it, no action is needed.</p>"
        ),
        cta_label="Open my album",
        cta_url=album_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def printer_download_url(order_id: str, token: str) -> str:
    return f"{FRONTEND_URL}/printer/{order_id}/download?token={token}"


def printer_ready_url(order_id: str, token: str) -> str:
    return f"{FRONTEND_URL}/printer/{order_id}?token={token}"


def send_printer_order_email(order: dict, group: list = None):
    """Sent once an order's PDF is made (see services/print_groups.py: a
    customer's albums ordered together come in one email, `group`, lead
    first). Carries a signed download link per album (not the files — a
    full-resolution album PDF can easily be tens of MB, past what many
    inboxes accept) and one signed "ready for delivery" link the printer
    opens once the books are done, which is what notifies the delivery
    company — see send_delivery_pickup_email."""
    group = group or [order]
    if not PRINTER_EMAIL:
        logger.warning(f"PRINTER_EMAIL non configuré — email d'impression non envoyé pour la commande {order['id']}")
        return
    if len(group) > 1:
        return _send_printer_group_email(group)
    download_token = sign_order_action(order["id"], "download")
    ready_token = sign_order_action(order["id"], "ready")
    # Links on the site's own address, not the server's (…run.app): mail
    # filters (Outlook above all) drop emails whose links lead to a hosting
    # address they don't know, while showing them as delivered.
    download_url = printer_download_url(order["id"], download_token)
    ready_url = printer_ready_url(order["id"], ready_token)
    subject = f"New book to print — {order.get('album_title', 'Album')} ({order_number(order)})"
    number = order_number(order)
    # No price anywhere in what the printer receives — only what's needed
    # to print. The number to write on the package is the courier's
    # (Wakilni's order number): it only exists once the printer confirms,
    # and the page shows it then.
    body = (
        f"New order to print.\n\n"
        f"Reference: {number}\n"
        f"Don't write anything on the package yet: the number to write on it is shown when you confirm below.\n\n"
        f"Album: {order.get('album_title', 'Album')}\n"
        f"Format: {order.get('size')} · {order.get('orientation')}\n"
        f"Quantity: {order.get('quantity', 1)}\n\n"
        f"Download the print-ready PDF:\n{download_url}\n\n"
        f"Once printed and packed, open this page and confirm — it then shows the number to write on the package:\n{ready_url}"
    )
    # Two calls to action here, not one — the shared wrapper's single
    # cta_label/cta_url slot only fits one, so both buttons are built by
    # hand instead, matching the wrapper's own button styling.
    two_button_html = _printer_button(download_url, "Download print-ready PDF", _EMAIL_INK, "28px") + _printer_button(
        ready_url, "Mark ready for delivery", _EMAIL_CORAL, "14px"
    )
    html_body = _email_wrapper(
        preheader=f"New book to print — {_h(order.get('album_title', 'Album'))}",
        title="New book to print.",
        body_html=(
            f"<p style=\"font-size:18px; font-weight:bold; letter-spacing:1px; margin:0 0 4px;\">Reference: {number}</p>"
            f"<p style=\"color:{_EMAIL_MUTED}; margin:0 0 18px;\">Don't write anything on the package yet: once it's printed and packed, "
            f"click \"Mark ready for delivery\" — the page then shows the number to write on it.</p>"
            f"<p><strong>Album:</strong> {_h(order.get('album_title', 'Album'))}<br>"
            f"<strong>Format:</strong> {order.get('size')} · {order.get('orientation')}<br>"
            f"<strong>Quantity:</strong> {order.get('quantity', 1)}</p>"
            f"{two_button_html}"
        ),
    )
    send_email(PRINTER_EMAIL, subject, body, html_body=html_body)


def _printer_button(url: str, label: str, color: str, margin_top: str) -> str:
    return f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin: {margin_top} 0 0;">
          <tr><td style="background-color:{color}; border-radius:2px;">
            <a href="{url}" style="display:inline-block; padding:14px 28px; color:{_EMAIL_PAPER}; text-decoration:none; font-family:{_EMAIL_SANS}; font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase;">{label}</a>
          </td></tr>
        </table>
    """


def _send_printer_group_email(group: list):
    """Several albums for one customer: printed, packed together in one
    package and marked ready with one click (which shows the courier's
    number to write on it)."""
    lead = group[0]
    number = order_number(lead)
    ready_url = printer_ready_url(lead["id"], sign_order_action(lead["id"], "ready"))
    books = sum(int(o.get("quantity") or 1) for o in group)
    subject = f"New books to print — {len(group)} albums, one package ({number})"
    lines, rows = [], []
    for i, o in enumerate(group, 1):
        url = printer_download_url(o["id"], sign_order_action(o["id"], "download"))
        lines.append(
            f"{i}. {o.get('album_title', 'Album')} ({order_number(o)}) — {o.get('size')} · {o.get('orientation')} · quantity {o.get('quantity', 1)}\n"
            f"   Download the print-ready PDF: {url}"
        )
        rows.append(
            f"<p style=\"margin:18px 0 0;\"><strong>{i}. {_h(o.get('album_title', 'Album'))}</strong> ({order_number(o)})<br>"
            f"{o.get('size')} · {o.get('orientation')} · Quantity: {o.get('quantity', 1)}<br>"
            f'<a href="{url}">Download print-ready PDF</a></p>'
        )
    body = (
        f"New order to print: {len(group)} albums for the same customer, delivered together.\n\n"
        f"ONE PACKAGE — reference: {number}\n"
        f"Please put all {books} books in one package. Don't write anything on it yet: the number to write on it is shown when you confirm below.\n\n"
        + "\n\n".join(lines)
        + f"\n\nOnce they're all printed and packed, open this page and confirm (once for all) — it then shows the number to write on the package:\n{ready_url}"
    )
    html_body = _email_wrapper(
        preheader=f"New books to print — {len(group)} albums, one package",
        title="New books to print.",
        body_html=(
            f"<p style=\"font-size:18px; font-weight:bold; letter-spacing:1px; margin:0 0 4px;\">One package — reference: {number}</p>"
            f"<p style=\"color:{_EMAIL_MUTED}; margin:0 0 18px;\">{len(group)} albums for the same customer, delivered together. "
            f"Please put all {books} books in one package. Don't write anything on it yet: the number to write on it is shown when you confirm.</p>"
            + "".join(rows)
            + "<p style=\"margin:28px 0 0;\">Once they're all printed and packed, confirm once for all — the page then shows the number to write on the package:</p>"
            + _printer_button(ready_url, "Mark all ready for delivery", _EMAIL_CORAL, "14px")
        ),
    )
    send_email(PRINTER_EMAIL, subject, body, html_body=html_body)

def send_delivery_pickup_email(order: dict, group: list = None):
    """Sent the moment the printer clicks their "ready for delivery" link
    — the delivery company only ever needs the shipping details, never the
    PDF or any account/order-management access."""
    if not DELIVERY_EMAIL:
        logger.warning(f"DELIVERY_EMAIL non configuré — email de livraison non envoyé pour la commande {order['id']}")
        return
    addr = order.get("shipping_address") or {}
    # Albums ordered together (see services/print_groups.py): one package.
    quantity = sum(int(o.get("quantity") or 1) for o in (group or [order]))
    subject = f"Ready for pickup — {order.get('album_title', 'Album')} ({order_number(order)})"
    body = (
        f"A book is ready for pickup and delivery.\n\n"
        f"Order number: {order_number(order)} (written on the package)\n\n"
        f"Deliver to:\n"
        f"{addr.get('full_name', '')}\n"
        f"{addr.get('street', '')}"
        + (f", {addr.get('building')}" if addr.get("building") else "")
        + f"\n{addr.get('city', '')}\n"
        f"Phone: {addr.get('phone', '')}\n"
        + (f"Notes: {addr.get('additional_info')}\n" if addr.get("additional_info") else "")
        + f"\nQuantity: {quantity}"
    )
    html_body = _email_wrapper(
        preheader=f"Ready for pickup — {_h(order.get('album_title', 'Album'))}",
        title="Ready for pickup.",
        body_html=(
            f"<p>A book is ready for pickup and delivery.</p>"
            f"<p><strong>Order number:</strong> {order_number(order)} (written on the package)</p>"
            f"<p><strong>Deliver to:</strong><br>"
            f"{_h(addr.get('full_name', ''))}<br>"
            f"{_h(addr.get('street', ''))}" + (f", {_h(addr.get('building'))}" if addr.get("building") else "") + f"<br>"
            f"{_h(addr.get('city', ''))}<br>"
            f"Phone: {_h(addr.get('phone', ''))}</p>"
            + (f"<p><strong>Notes:</strong> {_h(addr.get('additional_info'))}</p>" if addr.get("additional_info") else "")
            + f"<p><strong>Quantity:</strong> {quantity}</p>"
        ),
    )
    send_email(DELIVERY_EMAIL, subject, body, html_body=html_body)


def send_delivery_problem_email(order: dict, problem: str):
    """To the admin: a Wakilni delivery couldn't be created, or the courier
    reports a problem (failed, declined, postponed, rejected…)."""
    if not ADMIN_EMAIL:
        logger.warning(f"ADMIN_EMAIL non configuré — alerte de livraison non envoyée pour la commande {order['id']} : {problem}")
        return
    addr = order.get("shipping_address") or {}
    delivery = order.get("delivery") or {}
    subject = f"Delivery problem — order {order_number(order)} ({order.get('album_title', 'Album')})"
    lines = [
        f"Order {order_number(order)} — {order.get('album_title', 'Album')}",
        f"Problem: {problem}",
        f"Customer: {addr.get('full_name', '')}, {addr.get('phone', '')}",
        f"Address: {addr.get('street', '')}, {addr.get('area') or addr.get('city', '')}",
    ]
    if delivery.get("tracking_id"):
        lines.append(f"Wakilni tracking: {delivery.get('tracking_id')} {delivery.get('tracking_url') or ''}")
    body = "\n".join(lines) + f"\n\nAdmin: {FRONTEND_URL}/admin/orders"
    html_body = _email_wrapper(
        preheader=f"Delivery problem — {_h(problem)}",
        title="Delivery problem.",
        body_html="".join(f"<p>{_h(line)}</p>" for line in lines),
        cta_label="Open the orders",
        cta_url=f"{FRONTEND_URL}/admin/orders",
    )
    send_email(ADMIN_EMAIL, subject, body, html_body=html_body)


TEAM_EVENTS = {
    "ready": ("Ready for pickup", "The printer has marked this book ready: the courier has been asked to collect it."),
    "delivered": ("Delivered", "This order has been delivered to the customer."),
}


def send_team_order_update_email(order: dict, event: str):
    """To the team's order inbox (ORDERS_EMAIL): a step of an order —
    "ready" (the printer's click) or "delivered"."""
    if not ORDERS_EMAIL or event not in TEAM_EVENTS:
        return
    label, sentence = TEAM_EVENTS[event]
    number = order_number(order)
    addr = order.get("shipping_address") or {}
    delivery = order.get("delivery") or {}
    lines = [
        f"Order {number} — {order.get('album_title', 'Album')}",
        sentence,
        f"Customer: {addr.get('full_name', '')}, {addr.get('phone', '')}",
        f"Address: {addr.get('street', '')}{', ' + addr['building'] if addr.get('building') else ''}, {addr.get('area') or addr.get('city', '')}",
    ]
    if delivery.get("delivery_id"):
        lines.append(f"Wakilni: {delivery.get('status_label') or 'created'} — waybill {delivery.get('waybill') or number}"
                     + (f" — {delivery['tracking_url']}" if delivery.get("tracking_url") else ""))
    elif delivery.get("error"):
        lines.append(f"Wakilni: NOT created — {delivery['error'][:200]}")
    subject = f"[{label}] {number} — {order.get('album_title', 'Album')}"
    body = "\n".join(lines) + f"\n\nAdmin: {FRONTEND_URL}/admin/orders"
    html_body = _email_wrapper(
        preheader=f"{label} — {number}",
        title=f"{label}.",
        body_html="".join(f"<p>{_h(line)}</p>" for line in lines),
        cta_label="Open the orders",
        cta_url=f"{FRONTEND_URL}/admin/orders",
    )
    send_email(ORDERS_EMAIL, subject, body, html_body=html_body)
