import email

from jarvis import mail


def test_draft_url_is_encoded():
    url = mail.draft_url("teacher@school.org", "Sick today", "Hi,\nI'm ill & can't come in.")
    assert url.startswith("mailto:teacher@school.org?")
    assert "subject=Sick%20today" in url
    assert "%26" in url and "%0A" in url


def test_imap_host_from_address(monkeypatch):
    assert mail.imap_host("me@gmail.com") == "imap.gmail.com"
    assert mail.imap_host("me@icloud.com") == "imap.mail.me.com"


def test_html_only_email_body_is_flattened():
    raw = (
        "Content-Type: text/html; charset=utf-8\n\n"
        "<html><style>p{}</style><p>Hello <b>there</b></p></html>"
    )
    assert mail._body(email.message_from_string(raw)) == "Hello there"
