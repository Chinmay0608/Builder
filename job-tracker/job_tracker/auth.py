"""
IMAP authentication for Gmail.

Reads EMAIL_USERNAME and EMAIL_PASSWORD from environment / .env file.
EMAIL_PASSWORD should be a Google App Password (not your real Gmail password).

How to create a Google App Password:
  1. Go to https://myaccount.google.com/security
  2. Under "How you sign in to Google" -> enable 2-Step Verification (if not already)
  3. Search "App passwords" in the search bar at the top
  4. App name: "job-tracker"  -> click Create
  5. Copy the 16-character password (spaces don't matter)
  6. Add to your .env:
       EMAIL_USERNAME=you@gmail.com
       EMAIL_PASSWORD=xxxx xxxx xxxx xxxx
"""

from __future__ import annotations
import imaplib
import os
import pathlib


_GMAIL_IMAP_HOST = "imap.gmail.com"
_GMAIL_IMAP_PORT = 993


def _load_dotenv() -> None:
    """Load .env from CWD or any parent directory (no external deps)."""
    for directory in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        env_file = directory / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            break


def get_imap_connection() -> imaplib.IMAP4_SSL:
    """
    Return an authenticated IMAP4_SSL connection to Gmail.
    Reads EMAIL_USERNAME and EMAIL_PASSWORD from the environment.
    """
    _load_dotenv()

    username = os.environ.get("EMAIL_USERNAME", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").replace(" ", "").strip()

    if not username:
        raise ValueError(
            "EMAIL_USERNAME not set. Add it to your .env file:\n"
            "  EMAIL_USERNAME=you@gmail.com"
        )
    if not password:
        raise ValueError(
            "EMAIL_PASSWORD not set. Add your Google App Password to .env:\n"
            "  EMAIL_PASSWORD=xxxx xxxx xxxx xxxx"
        )

    mail = imaplib.IMAP4_SSL(_GMAIL_IMAP_HOST, _GMAIL_IMAP_PORT)
    mail.login(username, password)
    return mail


def get_username() -> str:
    """Return the Gmail username from environment."""
    _load_dotenv()
    return os.environ.get("EMAIL_USERNAME", "").strip()
