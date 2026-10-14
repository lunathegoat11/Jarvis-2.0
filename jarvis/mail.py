"""Reading email over IMAP, and drafting replies for you to send.

Jarvis never sends email itself. draft() opens a ready-to-send message in
your mail app, and you press Send. Reading uses an app password, not your
normal one: Gmail and iCloud both make these in their account settings.
"""

import email
import email.header
import email.message
import email.utils
import imaplib
import re
import urllib.parse
from dataclasses import dataclass

from .config import config

IMAP_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
    "mac.com": "imap.mail.me.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
}


def imap_host(address: str) -> str:
    if config.email_imap_host:
        return config.email_imap_host
    domain = address.rsplit("@", 1)[-1].lower()
    if domain not in IMAP_HOSTS:
        raise RuntimeError(
            f"I don't know the mail server for {domain}. Set EMAIL_IMAP_HOST in .env."
        )
    return IMAP_HOSTS[domain]


def configured() -> bool:
    return bool(config.email_address and config.email_app_password)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    return "".join(
        text.decode(charset or "utf-8", errors="replace") if isinstance(text, bytes) else text
        for text, charset in parts
    )


def _body(message: email.message.Message) -> str:
    """Plain-text body, or HTML with the tags stripped if there's no plain part."""
    html = ""
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain":
            return text.strip()
        if part.get_content_type() == "text/html" and not html:
            html = text
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Summary:
    id: str
    sender: str
    subject: str
    date: str
    unread: bool


def _connect() -> imaplib.IMAP4_SSL:
    if not configured():
        raise RuntimeError(
            "Email isn't set up. Add EMAIL_ADDRESS and EMAIL_APP_PASSWORD to .env."
        )
    conn = imaplib.IMAP4_SSL(imap_host(config.email_address))
    conn.login(config.email_address, config.email_app_password)
    conn.select("INBOX", readonly=True)  # read-only: nothing gets marked as read
    return conn


def recent(count: int = 5, unread_only: bool = False) -> list[Summary]:
    count = max(1, min(20, count))
    conn = _connect()
    try:
        _, data = conn.uid("search", None, "UNSEEN" if unread_only else "ALL")
        uids = data[0].split()[-count:][::-1]
        summaries = []
        for uid in uids:
            _, fetched = conn.uid(
                "fetch", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            header = email.message_from_bytes(fetched[0][1])
            flags = fetched[0][0].decode(errors="replace")
            name, addr = email.utils.parseaddr(_decode(header["From"]))
            summaries.append(
                Summary(
                    id=uid.decode(),
                    sender=name or addr,
                    subject=_decode(header["Subject"]) or "(no subject)",
                    date=_decode(header["Date"]),
                    unread="\\Seen" not in flags,
                )
            )
        return summaries
    finally:
        conn.logout()


def read(uid: str, max_chars: int = 4000) -> str:
    conn = _connect()
    try:
        _, fetched = conn.uid("fetch", uid.encode(), "(BODY.PEEK[])")
        if not fetched or fetched[0] is None:
            raise RuntimeError(f"No email with id {uid}.")
        message = email.message_from_bytes(fetched[0][1])
    finally:
        conn.logout()
    body = _body(message)
    if len(body) > max_chars:
        body = body[:max_chars] + " [...]"
    return (
        f"From: {_decode(message['From'])}\n"
        f"Subject: {_decode(message['Subject'])}\n"
        f"Date: {_decode(message['Date'])}\n\n{body}"
    )


def draft_url(to: str, subject: str, body: str) -> str:
    query = urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{urllib.parse.quote(to, safe='@,')}?{query}"


def draft(to: str, subject: str, body: str) -> None:
    """Opens a filled-in message in the default mail app, ready for you to send."""
    import subprocess
    import webbrowser

    url = draft_url(to, subject, body)
    if config.is_mac:
        subprocess.run(["open", url], check=True)
    else:
        webbrowser.open(url)
