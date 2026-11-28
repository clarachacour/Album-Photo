"""Every email the app sends (customers, printer, delivery)."""
import html
import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from app.config import (
    ADMIN_EMAIL,
    BACKEND_URL,
    DELIVERY_EMAIL,
    ALBUM_EXPIRING_WARNING_DAYS_BEFORE,
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


def sender() -> tuple:
    """(From header, address): the customer sees "Everbook" as the sender's
    name, whatever SMTP_FROM holds (an address alone showed its first part,
    "orders", in mail apps). A name written in SMTP_FROM itself
    ("Everbook <orders@…>") is kept."""
    name, address = parseaddr(SMTP_FROM)
    return formataddr((name or "Everbook", address)), address


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
        from_header, from_address = sender()
        msg["From"] = from_header
        msg["To"] = to_email
        # Standard headers Python doesn't add on its own: spam filters
        # (Outlook especially) mark down an email without them.
        msg["Date"] = formatdate(localtime=False)
        sender_domain = from_address.rpartition("@")[2] or None
        msg["Message-ID"] = make_msgid(domain=sender_domain)
        if reply_to:
            # "Reply" in the mail app then writes to this address (the
            # customer, for the contact form) instead of to the site.
            msg["Reply-To"] = " ".join(str(reply_to).split())
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(from_address, [to_email], msg.as_string())
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

def _email_wrapper(title: str, body_html: str, cta_label: str = None, cta_url: str = None, footer_html: str = "") -> str:
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

    body_html is HTML: every customer-typed value in it goes through _h()
    first. No hidden preview text: spam filters count invisible text
    against the email (SpamAssassin's FONT_INVIS_*)."""
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
          {f'<p style="font-family:{_EMAIL_SANS}; font-size:12px; color:{_EMAIL_MUTED}; margin:10px 0 0;">{footer_html}</p>' if footer_html else ""}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

def _fr(lang) -> bool:
    return lang == "fr"


def _hi(name, lang) -> str:
    """ "Hi Maya," / "Bonjour Maya," (no stray space without a name)."""
    return f"{'Bonjour' if _fr(lang) else 'Hi'} {name or ''},".replace(" ,", ",")


def _amount(value: float, currency: str, lang: str) -> str:
    """58.00 USD in English, 58,00 USD in French."""
    text = f"{value:.2f}"
    return f"{text.replace('.', ',') if _fr(lang) else text} {currency}"


def _home(lang) -> str:
    return f"{FRONTEND_URL}/fr" if _fr(lang) else FRONTEND_URL


def send_welcome_email(to_email: str, name: str, lang: str = "en"):
    """For a Google/Apple account (already confirmed): the welcome."""
    if _fr(lang):
        subject, title, cta = "Bienvenue sur Everbook", "Bienvenue sur Everbook.", "Commencer"
        text = ("Tout est prêt pour transformer vos photos en album imprimé. Importez vos photos, "
                "laissez-nous vous aider à les mettre en page, et commandez quand vous le souhaitez.")
    else:
        subject, title, cta = "Welcome to Everbook", "Welcome to Everbook.", "Get started"
        text = ("You're all set to start turning your photos into a printed album. Upload your photos, "
                "let us help you lay them out, and order whenever you're ready.")
    hi = _hi(name, lang)
    body = f"{hi}\n\n{text}\n\n{_home(lang)}"
    html_body = _email_wrapper(
        title=title,
        body_html=f"<p>{_h(hi)}</p><p>{_h(text)}</p>",
        cta_label=cta,
        cta_url=_home(lang),
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_verification_email(to_email: str, name: str, verify_token: str, welcome: bool = False, lang: str = "en"):
    """Sent right at signup (welcome=True — see signup) and again whenever
    resend_verification_email is called (welcome=False, a plain reminder
    rather than a second "welcome") — never for Google/Apple accounts,
    whose provider has already confirmed the address (see
    upsert_oauth_user). The link goes straight to a backend endpoint
    (verify_email) rather than a frontend page: one click is the whole
    interaction. welcome=True folds the account's very first email into
    this one, instead of a separate "Welcome to Everbook" alongside it."""
    verify_link = f"{BACKEND_URL}/api/auth/verify-email?token={verify_token}"
    if _fr(lang):
        subject = "Bienvenue sur Everbook — confirmez votre adresse e-mail" if welcome else "Confirmez votre adresse e-mail"
        title = "Bienvenue sur Everbook." if welcome else "Confirmez votre adresse e-mail."
        intro = (
            "Bienvenue sur Everbook, vous y êtes presque. Confirmez votre adresse e-mail pour finir de créer votre compte et commencer à transformer vos photos en album imprimé."
            if welcome else
            "Confirmez votre adresse e-mail pour finir de configurer votre compte."
        )
        ignore = "Si vous n'avez pas créé de compte Everbook, vous pouvez ignorer cet e-mail."
        cta = "Confirmer mon adresse e-mail"
    else:
        subject = "Welcome to Everbook — confirm your email" if welcome else "Confirm your email address"
        title = "Welcome to Everbook." if welcome else "Confirm your email address."
        intro = (
            "Welcome to Everbook — you're almost there. Please confirm your email address to finish creating your account and start turning your photos into a printed album."
            if welcome else
            "Please confirm your email address to finish setting up your account."
        )
        ignore = "If you didn't create an Everbook account, you can safely ignore this email."
        cta = "Confirm my email address"
    hi = _hi(name, lang)
    body = f"{hi}\n\n{intro}\n\n{verify_link}\n\n{ignore}"
    html_body = _email_wrapper(
        title=title,
        body_html=(
            f"<p>{_h(hi)}</p>"
            f"<p>{_h(intro)}</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">{_h(ignore)}</p>"
        ),
        cta_label=cta,
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

def send_password_reset_email(to_email: str, name: str, reset_link: str, lang: str = "en"):
    if _fr(lang):
        subject, title, cta = "Réinitialisez votre mot de passe", "Réinitialisez votre mot de passe.", "Réinitialiser mon mot de passe"
        plain = "Cliquez sur le lien ci-dessous pour réinitialiser votre mot de passe (valable 1 heure) :"
        text = "Cliquez sur le bouton ci-dessous pour réinitialiser votre mot de passe. Ce lien est valable 1 heure."
        ignore = "Si vous n'avez pas fait cette demande, vous pouvez ignorer cet e-mail."
    else:
        subject, title, cta = "Reset your password", "Reset your password.", "Reset my password"
        plain = "Click the link below to reset your password (valid for 1 hour):"
        text = "Click the button below to reset your password. This link is valid for 1 hour."
        ignore = "If you didn't request this, you can safely ignore this email."
    hi = _hi(name, lang)
    body = f"{hi}\n\n{plain}\n{reset_link}\n\n{ignore}"
    html_body = _email_wrapper(
        title=title,
        body_html=(
            f"<p>{_h(hi)}</p>"
            f"<p>{_h(text)}</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">{_h(ignore)}</p>"
        ),
        cta_label=cta,
        cta_url=reset_link,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_account_deleted_email(to_email: str, name: str, lang: str = "en"):
    """Confirms an account deletion, so the owner knows it happened (and
    can reach us if it wasn't them)."""
    if _fr(lang):
        subject, title = "Votre compte Everbook a été supprimé", "Votre compte a été supprimé."
        text = "Votre compte Everbook a été supprimé, ainsi que vos albums et vos photos."
        warn = "Si vous n'avez pas demandé cette suppression, contactez-nous immédiatement."
    else:
        subject, title = "Your Everbook account was deleted", "Your account was deleted."
        text = "Your Everbook account has been deleted, along with your albums and photos."
        warn = "If you didn't ask for this, please contact us right away."
    hi = _hi(name, lang)
    body = f"{hi}\n\n{text}\n\n{warn}"
    html_body = _email_wrapper(
        title=title,
        body_html=(
            f"<p>{_h(hi)}</p>"
            f"<p>{_h(text)}</p>"
            f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">{_h(warn)}</p>"
        ),
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_password_changed_email(to_email: str, name: str, lang: str = "en"):
    """A simple security notice, sent after a password change goes through
    (change_password or reset_password alike). Deliberately links nowhere:
    if this wasn't them, a link is what a phishing follow-up would look
    like."""
    if _fr(lang):
        subject, title = "Votre mot de passe Everbook a été modifié", "Votre mot de passe a été modifié."
        text = "Nous vous confirmons que le mot de passe de votre compte Everbook vient d'être modifié."
        warn = ("Si c'est bien vous, vous n'avez rien à faire. Sinon, contactez-nous immédiatement "
                "pour que nous vous aidions à sécuriser votre compte.")
    else:
        subject, title = "Your Everbook password was changed", "Your password was changed."
        text = "This is a confirmation that your Everbook account password was just changed."
        warn = ("If this was you, no action is needed. If you didn't make this change, "
                "please contact us right away so we can help secure your account.")
    hi = _hi(name, lang)
    body = f"{hi}\n\n{text}\n\n{warn}"
    html_body = _email_wrapper(
        title=title,
        body_html=f"<p>{_h(hi)}</p><p>{_h(text)}</p><p>{_h(warn)}</p>",
    )
    send_email(to_email, subject, body, html_body=html_body)

def _paid_online(order: dict) -> bool:
    """Paid online at checkout, Whish Pay or card (nothing to pay on delivery)."""
    return bool((order.get("payment") or {}).get("provider"))


def _paid_how(orders, lang: str = "en") -> str:
    """How it was paid, as the email says it: "by card" / "with Whish Pay"
    ("par carte" / "avec Whish Pay")."""
    orders = orders if isinstance(orders, list) else [orders]
    card = any((o.get("payment") or {}).get("provider") == "card" for o in orders)
    if _fr(lang):
        return "par carte" if card else "avec Whish Pay"
    return "by card" if card else "with Whish Pay"


def send_order_confirmation_email(to_email: str, name: str, order: dict, lang: str = "en"):
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    total = order.get("total_price_cents", 0) / 100
    if order.get("kind") == "digital":
        return _send_digital_order_confirmation_email(to_email, name, order, order_url, total, lang)
    money = _amount(total, order.get("currency", "usd").upper(), lang)
    quantity = order.get("quantity", 1)
    if _fr(lang):
        subject, title, cta = "Votre commande Everbook est confirmée", "Votre commande est confirmée.", "Suivre ma commande"
        thanks = "Merci pour votre commande ! Nous l'avons bien reçue et commençons à préparer votre album."
        paid = (
            f"Total de la commande : {money} (livraison comprise), payé {_paid_how(order, lang)}. Rien à payer à la livraison."
            if _paid_online(order) else
            f"Votre album est offert : vous ne payez que la livraison, {money}, en espèces au livreur."
            if not order.get("unit_price_cents") else
            f"Total de la commande : {money} (livraison comprise), à régler en espèces au livreur."
        )
        qty, follow, next_ = f"Quantité : {quantity}", "Suivez son avancement ici :", "Nous vous écrirons à nouveau dès son expédition."
    else:
        subject, title, cta = "Your Everbook order is confirmed", "Your order is confirmed.", "Track my order"
        thanks = "Thanks for your order! We've received it and will start preparing your album."
        paid = (
            f"Order total: {money} (delivery included), paid {_paid_how(order, lang)}. Nothing to pay on delivery."
            if _paid_online(order) else
            f"Your album is free: you only pay for delivery, {money}, in cash to the courier."
            if not order.get("unit_price_cents") else
            f"Order total: {money} (delivery included), to be paid in cash to the courier."
        )
        qty, follow, next_ = f"Quantity: {quantity}", "You can follow its status here:", "We'll email you again once it ships."
    hi = _hi(name, lang)
    body = f"{hi}\n\n{thanks}\n\n{paid}\n{qty}\n\n{follow}\n{order_url}\n\n{next_}"
    html_body = _email_wrapper(
        title=title,
        body_html=f"<p>{_h(hi)}</p><p>{_h(thanks)}</p><p>{_h(paid)}<br>{_h(qty)}</p><p>{_h(next_)}</p>",
        cta_label=cta,
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_checkout_confirmation_email(to_email: str, name: str, orders: list, lang: str = "en"):
    """One email for everything ordered together from the cart: each album
    and version, the total, how it's paid and what happens next."""
    fr = _fr(lang)
    currency = (orders[0].get("currency") or "usd").upper()
    prints = [o for o in orders if o.get("kind") != "digital"]
    digitals = [o for o in orders if o.get("kind") == "digital"]
    cash = _amount(sum(int(o.get("total_price_cents") or 0) for o in prints) / 100, currency, lang)
    paid_online = any(_paid_online(o) for o in orders)
    how = _paid_how(orders, lang)
    orders_url = f"{FRONTEND_URL}/orders"

    def line(o):
        if o.get("kind") == "digital":
            what = "PDF à télécharger" if fr else "PDF to download"
        else:
            what = f"{'album imprimé' if fr else 'printed album'} × {o.get('quantity', 1)}"
        return f"{o.get('album_title', 'Album')} — {what} ({order_number(o)})"

    notes = []
    if prints:
        many = len(prints) > 1
        if fr:
            where = "Vos albums imprimés seront livrés ensemble, dans un seul colis." if many else "Votre album imprimé vous sera livré à domicile."
            pay = (f"Commande payée {how} : rien à payer à la livraison." if paid_online else
                   f"Paiement à la livraison : le total, {cash} (livraison comprise), est à régler en espèces au livreur.")
        else:
            where = "Your printed albums will be delivered together, in one package." if many else "Your printed album will be delivered to your door."
            pay = (f"Paid {how}: nothing to pay on delivery." if paid_online else
                   f"Payment is cash on delivery: the total, {cash} (delivery included), is paid to the courier.")
        notes.append(f"{where} {pay}")
    if digitals:
        many = len(digitals) > 1
        free = not paid_online and not any(int(o.get("total_price_cents") or 0) for o in digitals)
        if fr:
            ready = ("Nous vous écrirons dès que vos PDF seront prêts à télécharger, dans quelques minutes." if many else
                     "Nous vous écrirons dès que votre PDF sera prêt à télécharger, dans quelques minutes.")
            lead = ("Vos PDF sont offerts. " if many else "Votre PDF est offert. ") if free else (f"Commande payée {how}. " if paid_online and not prints else "")
        else:
            ready = ("We'll email you as soon as your PDFs are ready to download, in a few minutes." if many else
                     "We'll email you as soon as your PDF is ready to download, in a few minutes.")
            lead = ("Your PDFs are free. " if many else "Your PDF is free. ") if free else (f"Paid {how}. " if paid_online and not prints else "")
        notes.append(lead + ready)
    if fr:
        subject = f"Votre commande Everbook est confirmée — {len(orders)} articles"
        title, cta = "Votre commande est confirmée.", "Suivre mes commandes"
        thanks = "Merci pour votre commande ! Nous l'avons bien reçue. Voici ce que vous avez commandé :"
        follow = "Suivez chacune d'elles ici :"
    else:
        subject = f"Your Everbook order is confirmed — {len(orders)} items"
        title, cta = "Your order is confirmed.", "Track my orders"
        thanks = "Thanks for your order! We've received it. Here's what you ordered:"
        follow = "You can follow each of them here:"
    hi = _hi(name, lang)
    body = (
        f"{hi}\n\n{thanks}\n\n"
        + "\n".join(f"- {line(o)}" for o in orders)
        + "\n\n" + "\n\n".join(notes)
        + f"\n\n{follow}\n{orders_url}"
    )
    html_body = _email_wrapper(
        title=title,
        body_html=(
            f"<p>{_h(hi)}</p>"
            f"<p>{_h(thanks)}</p>"
            "<ul>" + "".join(f"<li>{_h(line(o))}</li>" for o in orders) + "</ul>"
            + "".join(f"<p>{_h(n)}</p>" for n in notes)
        ),
        cta_label=cta,
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
        how = (
            f"La personne qui reçoit chaque carte saisit son code sur {FRONTEND_URL}/gift pour créer son album. Chaque carte est valable 12 mois."
            if many else
            f"La personne qui la reçoit saisit le code sur {FRONTEND_URL}/gift pour créer son album. Valable 12 mois."
        )
        line = lambda c: f"{c['code']} — album {c['size']} de {c['page_tier']} pages" + (f", pour {c['recipient_name']}" if c.get("recipient_name") else "")  # noqa: E731
        again = "Vous les retrouvez aussi dans « Commandes »." if many else "Vous la retrouvez aussi dans « Commandes »."
        cta = "Voir mes commandes"
    else:
        subject = "Your Everbook gift cards" if many else "Your Everbook gift card"
        intro = (
            "Thank you! Here are your gift cards, as PDFs: print them or send them on as they are."
            if many else
            "Thank you! Here's your gift card, as a PDF: print it or send it on as it is."
        )
        how = (
            f"Each recipient enters their code on {FRONTEND_URL}/gift to create their album. Each card is valid for 12 months."
            if many else
            f"The recipient enters the code on {FRONTEND_URL}/gift to create their album. Valid for 12 months."
        )
        line = lambda c: f"{c['code']} — {c['page_tier']}-page {c['size']} album" + (f", for {c['recipient_name']}" if c.get("recipient_name") else "")  # noqa: E731
        again = "You'll also find them in \"Orders\"." if many else "You'll also find it in \"Orders\"."
        cta = "See my orders"
    hello = _hi(name, "fr" if fr else "en")
    body = f"{hello}\n\n{intro}\n\n" + "".join(f"- {line(c)}\n" for c in cards) + f"\n{how}\n\n{again}\n{page_url}"
    html_body = _email_wrapper(
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

def _send_digital_order_confirmation_email(to_email: str, name: str, order: dict, order_url: str, total: float, lang: str = "en"):
    free = total == 0
    if _fr(lang):
        subject, title, cta = "Votre commande d'album numérique Everbook est confirmée", "Votre commande est confirmée.", "Voir ma commande"
        intro = (
            f"Merci pour votre commande ! Votre paiement {_paid_how(order, lang)} a bien été reçu. Votre album sera prêt à télécharger en PDF dans quelques minutes."
            if _paid_online(order) else
            "Merci pour votre commande ! Votre album numérique est offert : il sera prêt à télécharger en PDF dans quelques minutes."
            if free else
            "Merci pour votre commande ! Votre album sera prêt à télécharger en PDF dans quelques minutes."
        )
        follow, next_ = "Suivez votre commande ici :", "Nous vous écrirons à nouveau dès que votre PDF sera prêt."
    else:
        subject, title, cta = "Your Everbook digital album order is confirmed", "Your order is confirmed.", "View my order"
        intro = (
            f"Thanks for your order! Your payment {_paid_how(order, lang)} has been received. Your album will be ready to download as a PDF in a few minutes."
            if _paid_online(order) else
            "Thanks for your order! Your digital album is free: it will be ready to download as a PDF in a few minutes."
            if free else
            "Thanks for your order! Your album will be ready to download as a PDF in a few minutes."
        )
        follow, next_ = "You can follow your order here:", "We'll email you again as soon as your PDF is ready."
    hi = _hi(name, lang)
    body = f"{hi}\n\n{intro}\n\n{follow}\n{order_url}\n\n{next_}"
    html_body = _email_wrapper(
        title=title,
        body_html=f"<p>{_h(hi)}</p><p>{_h(intro)}</p><p>{_h(next_)}</p>",
        cta_label=cta,
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_digital_album_ready_email(to_email: str, name: str, order: dict, lang: str = "en"):
    """Sent once a digital album is paid and its PDF made (see
    deliver_digital_if_ready): the download is on the order's page."""
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    album_title = order.get("album_title") or "Album"
    if _fr(lang):
        subject = f"Votre album Everbook est prêt à télécharger — {album_title}"
        title, cta = "Votre album est prêt à télécharger.", "Télécharger mon album"
        intro = f"Votre album « {album_title} » est prêt ! Vous pouvez le télécharger en PDF depuis votre commande, autant de fois que vous le souhaitez."
        here, thanks = "Téléchargez-le ici :", "Merci d'avoir choisi Everbook."
    else:
        subject = f"Your Everbook album is ready to download — {album_title}"
        title, cta = "Your album is ready to download.", "Download my album"
        intro = f"Your album “{album_title}” is ready! You can download it as a PDF from your order, as many times as you like."
        here, thanks = "Download it here:", "Thanks for choosing Everbook."
    hi = _hi(name, lang)
    body = f"{hi}\n\n{intro}\n\n{here}\n{order_url}\n\n{thanks}"
    html_body = _email_wrapper(
        title=title,
        body_html=f"<p>{_h(hi)}</p><p>{_h(intro)}</p><p>{_h(thanks)}</p>",
        cta_label=cta,
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_shipped_email(to_email: str, name: str, order: dict, group: list = None, lang: str = "en"):
    """The album is on its way — or, for albums delivered together (`group`,
    see services/print_groups.py), all of them: one email for the package."""
    group = group or [order]
    many = len(group) > 1
    n = len(group)
    order_url = f"{FRONTEND_URL}/orders" if many else f"{FRONTEND_URL}/orders/{order['id']}"
    tracking = order.get("tracking_number")
    # The courier's own tracking page, when the delivery is a Wakilni one.
    tracking_url = (order.get("delivery") or {}).get("tracking_url")
    if _fr(lang):
        subject = f"Vos {n} albums Everbook sont en route" if many else "Votre commande Everbook est en route"
        news = (f"Bonne nouvelle : vos {n} albums ont été expédiés, ensemble dans un seul colis !" if many else
                "Bonne nouvelle : votre album a été expédié !")
        tracking_label, courier, courier_link = "Numéro de suivi :", "Suivez le livreur ici :", "Suivre le livreur"
        follow = "Suivez-les ici :" if many else "Suivez son avancement ici :"
        title, cta = "Votre commande a été expédiée.", ("Suivre mes commandes" if many else "Suivre ma commande")
    else:
        subject = f"Your {n} Everbook albums are on their way" if many else "Your Everbook order is on its way"
        news = (f"Good news — your {n} albums have shipped, together in one package!" if many else
                "Good news — your album has shipped!")
        tracking_label, courier, courier_link = "Tracking number:", "Follow the courier here:", "Follow the courier"
        follow = "You can follow them here:" if many else "You can follow its status here:"
        title, cta = "Your order has shipped.", ("Track my orders" if many else "Track my order")
    titles = [f"{o.get('album_title', 'Album')} ({order_number(o)})" for o in group]
    hi = _hi(name, lang)
    body = (
        f"{hi}\n\n{news}\n\n"
        + ("".join(f"- {t}\n" for t in titles) + "\n" if many else "")
        + (f"{tracking_label} {tracking}\n\n" if tracking else "")
        + (f"{courier}\n{tracking_url}\n\n" if tracking_url else "")
        + f"{follow}\n{order_url}"
    )
    html_body = _email_wrapper(
        title=title,
        body_html=(
            f"<p>{_h(hi)}</p>"
            f"<p>{_h(news)}</p>"
            + ("<ul>" + "".join(f"<li>{_h(t)}</li>" for t in titles) + "</ul>" if many else "")
            + (f"<p><strong>{_h(tracking_label)}</strong> {_h(tracking)}</p>" if tracking else "")
            + (f'<p><a href="{_h(tracking_url)}">{_h(courier_link)}</a></p>' if tracking_url else "")
        ),
        cta_label=cta,
        cta_url=order_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

def send_order_delivered_feedback_email(to_email: str, name: str, order: dict, group: list = None, lang: str = "en"):
    """Delivered: we ask how it turned out — for albums delivered together
    (`group`), one email with a feedback link per album."""
    group = group or [order]
    many = len(group) > 1
    n = len(group)
    feedback_url = f"{FRONTEND_URL}/orders/{order['id']}/feedback"
    contact_url = f"{FRONTEND_URL}/fr/contact" if _fr(lang) else f"{FRONTEND_URL}/contact"
    links = [(o.get("album_title", "Album"), f"{FRONTEND_URL}/orders/{o['id']}/feedback") for o in group]
    if _fr(lang):
        subject = "Vos albums Everbook vous plaisent ?" if many else "Votre album Everbook vous plaît ?"
        title = subject
        arrived = (f"Vos {n} albums devraient être arrivés : nous espérons qu'ils vous plaisent !" if many else
                   "Votre album devrait être arrivé : nous espérons qu'il vous plaît !")
        ask = "Nous aimerions beaucoup avoir votre avis sur chacun d'eux :" if many else "Nous aimerions beaucoup avoir votre avis :"
        problem_plain = "Si quelque chose ne va pas, contactez-nous et nous trouverons une solution :"
        problem_html = (f"Si quelque chose ne va pas, <a href=\"{contact_url}\" style=\"color:{_EMAIL_MUTED};\">contactez-nous</a> "
                        "et nous trouverons une solution.")
        thanks, cta = "Merci d'avoir choisi Everbook.", "Donner mon avis"
    else:
        subject = "How did your Everbook albums turn out?" if many else "How did your Everbook album turn out?"
        title = "How did your albums turn out?" if many else "How did your album turn out?"
        arrived = (f"Your {n} albums should have arrived by now — we hope you love them!" if many else
                   "Your album should have arrived by now — we hope you love it!")
        ask = "We'd love to hear what you thought of each one:" if many else "We'd love to hear what you thought:"
        problem_plain = "If anything wasn't right, please contact us and we'll sort it out:"
        problem_html = (f"If anything wasn't right, please <a href=\"{contact_url}\" style=\"color:{_EMAIL_MUTED};\">contact us</a> "
                        "and we'll sort it out.")
        thanks, cta = "Thank you for printing with Everbook.", "Share my feedback"
    hi = _hi(name, lang)
    body = (
        f"{hi}\n\n{arrived}\n\n"
        + (f"{ask}\n" + "".join(f"- {t}: {u}\n" for t, u in links) + "\n" if many else f"{ask}\n{feedback_url}\n\n")
        + f"{problem_plain}\n{contact_url}\n\n{thanks}"
    )
    html_body = _email_wrapper(
        title=title,
        body_html=(
            f"<p>{_h(hi)}</p>"
            f"<p>{_h(arrived)}</p>"
            + (
                f"<p>{_h(ask)}</p><ul>"
                + "".join(f'<li><a href="{_h(u)}">{_h(t)}</a></li>' for t, u in links)
                + "</ul>"
                if many else
                f"<p>{_h(ask.rstrip(':').rstrip())}.</p>"
            )
            + f"<p style=\"font-size:13px; color:{_EMAIL_MUTED};\">{problem_html}</p>"
        ),
        cta_label=cta,
        cta_url=feedback_url,
    )
    send_email(to_email, subject, body, html_body=html_body)

# Reminders (see services/reminders.py), in the customer's language, each
# with a link to stop them.
_REMINDER_TEXT = {
    "en": {
        "hi": "Hi {name},",
        "stop": "Don't want these reminders anymore? <a href=\"{url}\" style=\"color:inherit;\">Unsubscribe</a>.",
        "stop_plain": "Don't want these reminders anymore? Unsubscribe: {url}",
        "album_subject": "Finish your Everbook album — {title}",
        "album_title": "Finish your album.",
        "album_body": "You started \"{title}\" but haven't ordered it yet. It's saved just as you left it: it only takes a few minutes to finish it and order your printed album.",
        "album_cta": "Pick up where you left off",
        "cart_subject": "Your Everbook cart is waiting",
        "cart_title": "Your cart is waiting.",
        "cart_body": "You left this in your cart:",
        "cart_after": "Everything is saved: you can order whenever you like.",
        "cart_cta": "See my cart",
        "print": "printed album", "digital": "PDF album", "gift": "gift card",
    },
    "fr": {
        "hi": "Bonjour {name},",
        "stop": "Vous ne souhaitez plus recevoir ces rappels ? <a href=\"{url}\" style=\"color:inherit;\">Se désabonner</a>.",
        "stop_plain": "Vous ne souhaitez plus recevoir ces rappels ? Se désabonner : {url}",
        "album_subject": "Terminez votre album Everbook — {title}",
        "album_title": "Terminez votre album.",
        "album_body": "Vous avez commencé « {title} » mais ne l'avez pas encore commandé. Il est enregistré tel que vous l'avez laissé : quelques minutes suffisent pour le terminer et commander votre album imprimé.",
        "album_cta": "Reprendre mon album",
        "cart_subject": "Votre panier Everbook vous attend",
        "cart_title": "Votre panier vous attend.",
        "cart_body": "Vous avez laissé dans votre panier :",
        "cart_after": "Tout est enregistré : vous pouvez commander quand vous voulez.",
        "cart_cta": "Voir mon panier",
        "print": "album imprimé", "digital": "album en PDF", "gift": "carte cadeau",
    },
}


def _reminder_text(lang: str) -> dict:
    return _REMINDER_TEXT["fr" if lang == "fr" else "en"]


def send_unfinished_album_reminder_email(to_email: str, name: str, album: dict, stop_url: str = None):
    t = _reminder_text(album.get("lang"))
    album_url = f"{FRONTEND_URL}/editor/{album['id']}"
    title = album.get("title") or "Album"
    hi = t["hi"].format(name=name or "").replace(" ,", ",")
    body = f"{hi}\n\n{t['album_body'].format(title=title)}\n\n{album_url}"
    if stop_url:
        body += "\n\n" + t["stop_plain"].format(url=stop_url)
    html_body = _email_wrapper(
        title=t["album_title"],
        body_html=f"<p>{_h(hi)}</p><p>{_h(t['album_body'].format(title=title))}</p>",
        cta_label=t["album_cta"],
        cta_url=album_url,
        footer_html=t["stop"].format(url=stop_url) if stop_url else "",
    )
    send_email(to_email, t["album_subject"].format(title=title), body, html_body=html_body)


def send_cart_reminder_email(to_email: str, name: str, lines: list, lang: str, stop_url: str = None):
    """lines: [(title, kind)] — what's in the cart (kind: print, digital, gift)."""
    t = _reminder_text(lang)
    cart_url = f"{FRONTEND_URL}/cart"
    hi = t["hi"].format(name=name or "").replace(" ,", ",")
    listed = [f"{title} — {t.get(kind, kind)}" for title, kind in lines]
    body = f"{hi}\n\n{t['cart_body']}\n" + "\n".join(f"• {line}" for line in listed) + f"\n\n{t['cart_after']}\n\n{cart_url}"
    if stop_url:
        body += "\n\n" + t["stop_plain"].format(url=stop_url)
    html_body = _email_wrapper(
        title=t["cart_title"],
        body_html=(
            f"<p>{_h(hi)}</p><p>{_h(t['cart_body'])}</p>"
            "<ul style=\"padding-left:20px;\">" + "".join(f"<li>{_h(line)}</li>" for line in listed) + "</ul>"
            f"<p>{_h(t['cart_after'])}</p>"
        ),
        cta_label=t["cart_cta"],
        cta_url=cart_url,
        footer_html=t["stop"].format(url=stop_url) if stop_url else "",
    )
    send_email(to_email, t["cart_subject"], body, html_body=html_body)

_EXPIRING_TEXT = {
    "en": {
        "subject": "\"{title}\" will be deleted in {days}",
        "title": "Your album will be deleted soon.",
        "body": "\"{title}\" hasn't been ordered or changed for {retention} days or more. To free up space, albums that are never ordered are deleted, along with their photos.",
        "when": "It will be deleted in {days}. To keep it, open it and make a change (or order it) before then. If you don't need it anymore, you don't need to do anything.",
        "cta": "Open my album",
        "day": "1 day", "days": "{n} days",
    },
    "fr": {
        "subject": "« {title} » sera supprimé dans {days}",
        "title": "Votre album sera bientôt supprimé.",
        "body": "« {title} » n'a été ni commandé ni modifié depuis {retention} jours ou plus. Pour libérer de la place, les albums jamais commandés sont supprimés, avec leurs photos.",
        "when": "Il sera supprimé dans {days}. Pour le garder, ouvrez-le et faites une modification (ou commandez-le) d'ici là. Si vous n'en avez plus besoin, vous n'avez rien à faire.",
        "cta": "Ouvrir mon album",
        "day": "1 jour", "days": "{n} jours",
    },
}


def send_album_expiring_soon_email(to_email: str, name: str, album: dict, days_left: int):
    """The warning a few days before an album never ordered is deleted (see
    deletion_at in services/reminders.py), in the album's language."""
    t = _EXPIRING_TEXT["fr" if album.get("lang") == "fr" else "en"]
    hi = _reminder_text(album.get("lang"))["hi"].format(name=name or "").replace(" ,", ",")
    album_url = f"{FRONTEND_URL}/editor/{album['id']}"
    title = album.get("title") or "Album"
    days = t["day"] if days_left == 1 else t["days"].format(n=days_left)
    retention = DRAFT_ALBUM_RETENTION_DAYS - ALBUM_EXPIRING_WARNING_DAYS_BEFORE
    paragraph1 = t["body"].format(title=title, retention=retention)
    paragraph2 = t["when"].format(days=days)
    body = f"{hi}\n\n{paragraph1}\n\n{paragraph2}\n\n{album_url}"
    html_body = _email_wrapper(
        title=t["title"],
        body_html=f"<p>{_h(hi)}</p><p>{_h(paragraph1)}</p><p>{_h(paragraph2)}</p>",
        cta_label=t["cta"],
        cta_url=album_url,
    )
    send_email(to_email, t["subject"].format(title=title, days=days), body, html_body=html_body)


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


def send_payment_review_email(payment: dict, customer: dict, problem: str):
    """To the admin: an online payment (Whish Pay or card) went through but the cart couldn't
    be ordered as paid for (it changed meanwhile…): to order by hand, or to
    refund in the Whish account."""
    if not ADMIN_EMAIL:
        logger.warning(f"ADMIN_EMAIL non configuré — paiement {payment.get('id')} à vérifier : {problem}")
        return
    amount = (payment.get("amount_cents") or 0) / 100
    how = "card" if payment.get("provider") == "card" else "Whish Pay"
    subject = f"{'Card' if how == 'card' else 'Whish'} payment to check — {amount:.2f} USD"
    lines = [
        f"A {how} payment of {amount:.2f} USD went through, but nothing was ordered: {problem}.",
        f"Customer: {customer.get('name') or ''} {customer.get('email') or ''}".strip(),
        f"Reference: {payment.get('transaction_id') or payment.get('external_id')} (payment {payment.get('id')})",
        f"Paid at: {payment.get('paid_at') or ''}",
        f"Order it by hand with the customer, or refund it from the {'areeba (Cybersource)' if how == 'card' else 'Whish'} account.",
    ]
    body = "\n".join(lines)
    html_body = _email_wrapper(
        title="A payment to check.",
        body_html="".join(f"<p>{_h(line)}</p>" for line in lines),
        cta_label="Open the orders",
        cta_url=f"{FRONTEND_URL}/admin/orders",
    )
    send_email(ADMIN_EMAIL, subject, body, html_body=html_body)


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
        title="Delivery problem.",
        body_html="".join(f"<p>{_h(line)}</p>" for line in lines),
        cta_label="Open the orders",
        cta_url=f"{FRONTEND_URL}/admin/orders",
    )
    send_email(ADMIN_EMAIL, subject, body, html_body=html_body)


def send_team_new_order_email(orders: list, customer: dict):
    """To the team's order inbox (ORDERS_EMAIL): an order just placed — one
    email for everything ordered together (a cart's albums), with who, where
    and what the courier collects."""
    if not ORDERS_EMAIL or not orders:
        return
    from app.services.wakilni import cash_due

    currency = (orders[0].get("currency") or "usd").upper()
    money = lambda cents: f"{(cents or 0) / 100:.2f} {currency}"  # noqa: E731
    prints = [o for o in orders if o.get("kind") != "digital"]
    lead = (prints or orders)[0]
    number = order_number(lead)
    addr = lead.get("shipping_address") or {}
    name = addr.get("full_name") or customer.get("name") or ""

    def album(o):
        what = "PDF" if o.get("kind") == "digital" else f"printed × {o.get('quantity', 1)}"
        return f"{o.get('album_title', 'Album')} — {what}, {o.get('size', '')} {o.get('orientation', '')} ({order_number(o)})"

    lines = [f"Customer: {name} — {customer.get('email', '')}" + (f" — {addr['phone']}" if addr.get("phone") else "")]
    if prints:
        lines.append(f"Address: {addr.get('street', '')}{', ' + addr['building'] if addr.get('building') else ''}, "
                     f"{addr.get('area') or ''}{', ' if addr.get('area') else ''}{addr.get('city', '')}"
                     + (f" ({addr['additional_info']})" if addr.get("additional_info") else ""))
    lines.append("Albums:")
    lines += [f"- {album(o)}" for o in orders]
    shipping = sum(int(o.get("shipping_price_cents") or 0) for o in prints)
    if shipping:
        lines.append(f"Delivery: {money(shipping)}")
    promo = next((o for o in orders if o.get("promo_code")), None)
    if promo:
        lines.append(f"Promo code {promo['promo_code']}: −{money(sum(int(o.get('promo_discount_cents') or 0) for o in orders))}")
    credit = sum(int(o.get("gift_credit_cents") or 0) for o in orders)
    if credit:
        lines.append(f"Gift card credit: −{money(credit)}")
    paid_online = [o for o in orders if _paid_online(o)]
    if paid_online:
        lines.append(f"Paid online ({'card' if any((o.get('payment') or {}).get('provider') == 'card' for o in paid_online) else 'Whish Pay'}): {money(sum(int(o.get('total_price_cents') or 0) for o in paid_online))}")
    cash = sum(cash_due(o) for o in prints if not _paid_online(o))
    if prints:
        lines.append(f"To collect in cash by the courier: {money(cash)}")
    subject = f"[New order] {number} — {name or customer.get('email', '')} — {money(cash) if prints else 'PDF'}"
    body = "\n".join(lines) + f"\n\nAdmin: {FRONTEND_URL}/admin/orders"
    html_body = _email_wrapper(
        title="New order.",
        body_html="".join(f"<p>{_h(line)}</p>" for line in lines),
        cta_label="Open the orders",
        cta_url=f"{FRONTEND_URL}/admin/orders",
    )
    send_email(ORDERS_EMAIL, subject, body, html_body=html_body)


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
        title=f"{label}.",
        body_html="".join(f"<p>{_h(line)}</p>" for line in lines),
        cta_label="Open the orders",
        cta_url=f"{FRONTEND_URL}/admin/orders",
    )
    send_email(ORDERS_EMAIL, subject, body, html_body=html_body)
