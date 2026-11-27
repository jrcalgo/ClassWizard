"""Outgoing email over SMTP (Mailpit in development).

SMTP_HOST unset means email is off: signup still works, but verification and
password reset emails cannot be sent (GET /config reports email_enabled=false).
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage

from backend.accounts.settings import public_base_url


def enabled() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


def send(to: str, subject: str, body: str) -> bool:
    """Send one plain-text email. Returns False (and logs) on failure."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return False
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", "ClassWizard <no-reply@classwizard.local>")
    use_ssl = os.environ.get("SMTP_SSL", "0") == "1"
    use_starttls = os.environ.get("SMTP_STARTTLS", "0") == "1"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_cls(host, port, timeout=10) as smtp:
            if use_starttls and not use_ssl:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        print(f"email to {to!r} failed: {exc!r}", file=sys.stderr)
        return False
    return True


def send_verification(to: str, token: str) -> bool:
    link = f"{public_base_url()}/verify?token={token}"
    return send(
        to,
        "Confirm your ClassWizard email",
        "Welcome to ClassWizard.\n\n"
        f"Confirm your email address by opening this link:\n{link}\n\n"
        "The link expires in 48 hours. If you did not create an account, ignore this email.\n",
    )


def send_password_reset(to: str, token: str) -> bool:
    link = f"{public_base_url()}/reset?token={token}"
    return send(
        to,
        "Reset your ClassWizard password",
        "Someone asked to reset the password for this ClassWizard account.\n\n"
        f"Choose a new password here:\n{link}\n\n"
        "The link expires in 1 hour. If you did not ask for this, ignore this email; "
        "your password has not changed.\n",
    )
