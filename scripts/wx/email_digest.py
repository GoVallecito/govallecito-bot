"""
The daily email digest.

WHY THIS MATTERS MORE THAN FOLLOWER COUNT
Pagosa Weather -- the proof-of-concept 35 miles east, in a county a quarter the
size -- runs ~900 daily emails alongside 9,000 Facebook followers. The email
list is the durable half. A Facebook page is rented ground: reach is throttled
by an algorithm nobody controls and a policy change can halve it overnight. An
email list is owned, portable, and it arrives whether or not Meta feels like
showing it.

SCALE, HONESTLY
The SMTP path below is fine for a few dozen recipients and NOT fine beyond
that. Gmail caps sends and, more importantly, bulk-sending from a personal
mailbox will hurt deliverability for the address David actually uses. Past
roughly 50 subscribers, move to a real list provider -- Kit or Buttondown --
and use render() to produce the body while they handle sending, bounces and
unsubscribes. The migration is a couple of lines because rendering and sending
are deliberately separate here.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

from . import brand as BR
from . import constants as C

MAX_SMTP_RECIPIENTS = 50


def render(text, bundle, card_path=None):
    """Digest body. Returns (subject, plain_text, html)."""
    sl = bundle.get("snow_line") or {}
    alerts = bundle.get("alerts") or []

    if alerts:
        subject = f"{alerts[0]['event']} — {BR.SHORT}"
    elif sl.get("representative_ft"):
        subject = f"Snow line near {sl['representative_ft']:,} ft — {BR.SHORT}"
    else:
        subject = f"{bundle.get('local_date')} — {BR.SHORT}"

    lines = [text.strip(), ""]

    types = bundle.get("precip_type_by_band") or {}
    if types:
        lines.append("BY ELEVATION")
        for key in C.BAND_ORDER:
            t = types.get(key)
            if t:
                lines.append(f"  {t['label']} ({t['elevation_ft']:,} ft): {t['precip_type']}")
        lines.append("")

    srcs = sorted({(v or {}).get("source") for v in (bundle.get("sources") or {}).values()
                   if (v or {}).get("source")})
    if srcs:
        lines.append("Sources: " + ", ".join(srcs))
    lines.append("")
    lines.append(f"{BR.FOOTER_NOTE}")
    lines.append(f"https://{BR.SITE}")
    plain = "\n".join(lines)

    html = (
        f'<div style="max-width:38rem;margin:0 auto;font:16px/1.6 -apple-system,'
        f'Segoe UI,Roboto,sans-serif;color:#111821">'
        f'<p style="font-weight:700;margin:0">{BR.NAME}</p>'
        f'<p style="color:#5c6978;margin:.2rem 0 1.2rem">{BR.TAGLINE}</p>'
        + (f'<p style="background:#fdf1ef;border-left:4px solid #c43f2e;'
           f'padding:.7rem .9rem">Active: '
           f'{", ".join(a["event"] for a in alerts)}</p>' if alerts else "")
        + (f'<p style="font-size:1.6rem;font-weight:700;color:#c43f2e;margin:.6rem 0">'
           f'Snow line {sl["representative_ft"]:,} ft</p>'
           if sl.get("representative_ft") else "")
        + f'<div style="white-space:pre-wrap">{_escape(text.strip())}</div>'
        + (f'<p style="color:#5c6978;font-size:.85rem;margin-top:2rem">'
           f'Sources: {", ".join(srcs)}</p>' if srcs else "")
        + f'<p style="color:#5c6978;font-size:.85rem">{BR.FOOTER_NOTE}<br>'
          f'<a href="https://{BR.SITE}">{BR.SITE}</a></p></div>'
    )
    return subject, plain, html


def _escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def send(subject, plain, html, recipients, card_path=None):
    """Send via SMTP. Refuses to fan out past MAX_SMTP_RECIPIENTS.

    Honours DRY_RUN like everything else, and returns rather than raising --
    a failed digest must never take down the forecast that already published.
    """
    from .publish import is_dry_run

    recipients = [r for r in (recipients or []) if r]
    if not recipients:
        return {"skipped": "no recipients"}
    if len(recipients) > MAX_SMTP_RECIPIENTS:
        return {"skipped": (f"{len(recipients)} recipients exceeds the SMTP path's "
                            f"limit of {MAX_SMTP_RECIPIENTS} -- move to a list "
                            f"provider and use render() for the body")}
    if is_dry_run():
        print(f"DRY RUN -- would email {len(recipients)} recipient(s): {subject}")
        return {"dry_run": True, "recipients": len(recipients), "subject": subject}

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("WX_FROM", user)
    if not (user and password and sender):
        return {"skipped": "SMTP_USER / SMTP_PASSWORD / WX_FROM not configured"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{BR.NAME} <{sender}>"
    msg["To"] = sender
    # Recipients go in Bcc so subscribers never see each other's addresses.
    msg["Bcc"] = ", ".join(recipients)
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    if card_path and os.path.exists(card_path):
        with open(card_path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype="image", subtype="png",
                               filename=os.path.basename(card_path))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, password)
            s.send_message(msg)
        return {"sent": len(recipients)}
    except Exception as exc:  # noqa: BLE001
        print(f"[email] send failed: {exc}")
        return {"failed": str(exc)}


def load_recipients():
    """Subscribers from state/subscribers.txt, one address per line."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "state", "subscribers.txt")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [ln.strip() for ln in fh
                if ln.strip() and not ln.strip().startswith("#")]
