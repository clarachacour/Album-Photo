"""Every email the app sends (customers, printer, delivery)."""
import html
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    ADMIN_EMAIL,
    BACKEND_URL,
    DELIVERY_EMAIL,
    DRAFT_ALBUM_RETENTION_DAYS,
    FRONTEND_URL,
    PRINTER_EMAIL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)
from app.core.signed_links import sign_order_action

logger = logging.getLogger(__name__)


def _h(value) -> str:
    """Text typed by a customer (name, album title, address…), made safe to
    put in an HTML email: shown as text, never read as a link or markup."""
    return html.escape(str(value if value is not None else ""))


def send_email(to_email: str, subject: str, body: str, html_body: str = None):
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
        # Album titles and contact subjects end up here: a line break would
        # start a new header line.
        msg["Subject"] = " ".join(str(subject).split())
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
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
    subject = f"PDF generation failed — order #{order['id'][:8]} ({order.get('album_title', 'Album')})"
    body = (
        f"PDF generation failed for an order and needs attention.\n\n"
        f"Album: {order.get('album_title', 'Album')}\n"
        f"Order ID: {order['id']}\n"
        f"Size/pages: {order.get('size')} · {order.get('orientation')}\n\n"
        f"Error: {error}\n\n"
        f"Regenerate or investigate here:\n{admin_url}"
    )
    html_body = _email_wrapper(
        preheader=f"PDF generation failed for order #{order['id'][:8]}",
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
    subject = "Your Everbook order is confirmed"
    body = (
        f"Hi {name or ''},\n\n"
        f"Thanks for your order! We've received it and will start preparing your book.\n\n"
        f"Order total: {total:.2f} {order.get('currency', 'usd').upper()}\n"
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
            f"<p><strong>Order total:</strong> {total:.2f} {order.get('currency', 'usd').upper()}<br>"
            f"<strong>Quantity:</strong> {order.get('quantity', 1)}</p>"
            f"<p>We'll email you again once it ships.</p>"
        ),
        cta_label="Track your order",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_shipped_email(to_email: str, name: str, order: dict):
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    tracking = order.get("tracking_number")
    subject = "Your Everbook order is on its way"
    body = (
        f"Hi {name or ''},\n\n"
        f"Good news — your book has shipped!\n\n"
        + (f"Tracking number: {tracking}\n\n" if tracking else "")
        + f"You can follow its status here:\n{order_url}"
    )
    html_body = _email_wrapper(
        preheader="Good news — your book has shipped!",
        title="Your order has shipped.",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Good news — your book has shipped!</p>"
            + (f"<p><strong>Tracking number:</strong> {_h(tracking)}</p>" if tracking else "")
        ),
        cta_label="Track your order",
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_delivered_feedback_email(to_email: str, name: str, order: dict):
    feedback_url = f"{FRONTEND_URL}/orders/{order['id']}/feedback"
    contact_url = f"{FRONTEND_URL}/contact"
    subject = "How did your Everbook turn out?"
    body = (
        f"Hi {name or ''},\n\n"
        f"Your book should have arrived by now — we hope you love it!\n\n"
        f"We'd love to hear what you thought:\n{feedback_url}\n\n"
        f"If anything wasn't right, contact us instead:\n{contact_url}\n\n"
        f"Thank you for printing with Everbook."
    )
    html_body = _email_wrapper(
        preheader="Your book should have arrived by now — we hope you love it!",
        title="How did your book turn out?",
        body_html=(
            f"<p>Hi {_h(name or '')},</p>"
            f"<p>Your book should have arrived by now — we hope you love it!</p>"
            f"<p>We'd love to hear what you thought.</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">If anything wasn't right, "
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

def send_printer_order_email(order: dict):
    """Sent automatically the moment an order's PDF finishes generating.
    Carries a signed download link (not the file itself — a full-
    resolution album PDF can easily be tens of MB, well past what many
    inboxes accept as an attachment) and a signed "ready for delivery"
    link the printer clicks once the physical book is done, which is what
    actually notifies the delivery company — see send_delivery_pickup_email."""
    if not PRINTER_EMAIL:
        logger.warning(f"PRINTER_EMAIL non configuré — email d'impression non envoyé pour la commande {order['id']}")
        return
    download_token = sign_order_action(order["id"], "download")
    ready_token = sign_order_action(order["id"], "ready")
    download_url = f"{BACKEND_URL}/api/order-actions/{order['id']}/download?token={download_token}"
    ready_url = f"{BACKEND_URL}/api/order-actions/{order['id']}/ready?token={ready_token}"
    subject = f"New book to print — {order.get('album_title', 'Album')} (#{order['id'][:8]})"
    body = (
        f"New order to print.\n\n"
        f"Album: {order.get('album_title', 'Album')}\n"
        f"Format: {order.get('size')} · {order.get('orientation')}\n"
        f"Quantity: {order.get('quantity', 1)}\n\n"
        f"Download the print-ready PDF:\n{download_url}\n\n"
        f"Once printed and ready for the courier to collect, click here:\n{ready_url}"
    )
    # Two calls to action here, not one — the shared wrapper's single
    # cta_label/cta_url slot only fits one, so both buttons are built by
    # hand instead, matching the wrapper's own button styling (same
    # colors, same shape) for visual consistency rather than passing a
    # cta to the wrapper and losing the second action.
    two_button_html = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 28px 0 0;">
          <tr><td style="background-color:{_EMAIL_INK}; border-radius:2px;">
            <a href="{download_url}" style="display:inline-block; padding:14px 28px; color:{_EMAIL_PAPER}; text-decoration:none; font-family:{_EMAIL_SANS}; font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase;">Download print-ready PDF</a>
          </td></tr>
        </table>
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 14px 0 0;">
          <tr><td style="background-color:{_EMAIL_CORAL}; border-radius:2px;">
            <a href="{ready_url}" style="display:inline-block; padding:14px 28px; color:{_EMAIL_PAPER}; text-decoration:none; font-family:{_EMAIL_SANS}; font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase;">Mark ready for delivery</a>
          </td></tr>
        </table>
    """
    html_body = _email_wrapper(
        preheader=f"New book to print — {_h(order.get('album_title', 'Album'))}",
        title="New book to print.",
        body_html=(
            f"<p><strong>Album:</strong> {_h(order.get('album_title', 'Album'))}<br>"
            f"<strong>Format:</strong> {order.get('size')} · {order.get('orientation')}<br>"
            f"<strong>Quantity:</strong> {order.get('quantity', 1)}</p>"
            f"{two_button_html}"
        ),
    )
    send_email(PRINTER_EMAIL, subject, body, html_body=html_body)

def send_delivery_pickup_email(order: dict):
    """Sent the moment the printer clicks their "ready for delivery" link
    — the delivery company only ever needs the shipping details, never the
    PDF or any account/order-management access."""
    if not DELIVERY_EMAIL:
        logger.warning(f"DELIVERY_EMAIL non configuré — email de livraison non envoyé pour la commande {order['id']}")
        return
    addr = order.get("shipping_address") or {}
    subject = f"Ready for pickup — {order.get('album_title', 'Album')} (#{order['id'][:8]})"
    body = (
        f"A book is ready for pickup and delivery.\n\n"
        f"Deliver to:\n"
        f"{addr.get('full_name', '')}\n"
        f"{addr.get('street', '')}"
        + (f", {addr.get('building')}" if addr.get("building") else "")
        + f"\n{addr.get('city', '')}\n"
        f"Phone: {addr.get('phone', '')}\n"
        + (f"Notes: {addr.get('additional_info')}\n" if addr.get("additional_info") else "")
        + f"\nQuantity: {order.get('quantity', 1)}"
    )
    html_body = _email_wrapper(
        preheader=f"Ready for pickup — {_h(order.get('album_title', 'Album'))}",
        title="Ready for pickup.",
        body_html=(
            f"<p>A book is ready for pickup and delivery.</p>"
            f"<p><strong>Deliver to:</strong><br>"
            f"{_h(addr.get('full_name', ''))}<br>"
            f"{_h(addr.get('street', ''))}" + (f", {_h(addr.get('building'))}" if addr.get("building") else "") + f"<br>"
            f"{_h(addr.get('city', ''))}<br>"
            f"Phone: {_h(addr.get('phone', ''))}</p>"
            + (f"<p><strong>Notes:</strong> {_h(addr.get('additional_info'))}</p>" if addr.get("additional_info") else "")
            + f"<p><strong>Quantity:</strong> {order.get('quantity', 1)}</p>"
        ),
    )
    send_email(DELIVERY_EMAIL, subject, body, html_body=html_body)
