"""
IMAP authentication for Gmail with multi-account support.

Reads email credentials from environment / .env file.
Supports multiple accounts in .env:
  EMAIL_USER=chinmay8064@gmail.com
  EMAIL_PASSWORD=xxxx xxxx xxxx xxxx

  EMAIL_USER=chinmaymaheshwari.it27@gmail.com
  EMAIL_PASSWORD=yyyy yyyy yyyy yyyy
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


def get_accounts() -> list[tuple[str, str]]:
    """
    Find all email accounts configured in .env or environment.
    Returns list of (username, password) tuples.
    """
    accounts: list[tuple[str, str]] = []

    # Parse .env directly to collect multiple sequential blocks
    for directory in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:
        env_file = directory / ".env"
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()
            curr_user = None
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k in ("EMAIL_USER", "EMAIL_USERNAME") or k.startswith("EMAIL_USER_"):
                        curr_user = v
                    elif (k == "EMAIL_PASSWORD" or k.startswith("EMAIL_PASSWORD_")) and curr_user:
                        pwd = v.replace(" ", "").strip()
                        if (curr_user, pwd) not in accounts:
                            accounts.append((curr_user, pwd))
                        curr_user = None
            break

    # Fallback to single os.environ if no blocks found
    if not accounts:
        _load_dotenv()
        u = os.environ.get("EMAIL_USER") or os.environ.get("EMAIL_USERNAME", "").strip()
        p = os.environ.get("EMAIL_PASSWORD", "").replace(" ", "").strip()
        if u and p:
            accounts.append((u, p))

    return accounts


def get_imap_connection(username: str | None = None, password: str | None = None) -> imaplib.IMAP4_SSL:
    """
    Return an authenticated IMAP4_SSL connection to Gmail.
    If username/password are not given, uses the first account from get_accounts().
    """
    if not username or not password:
        accs = get_accounts()
        if not accs:
            raise ValueError(
                "No email accounts found in .env. Add:\n"
                "  EMAIL_USER=you@gmail.com\n"
                "  EMAIL_PASSWORD=xxxx xxxx xxxx xxxx"
            )
        username, password = accs[0]

    password_clean = password.replace(" ", "").strip()
    last_err = None
    for attempt in range(3):
        try:
            mail = imaplib.IMAP4_SSL(_GMAIL_IMAP_HOST, _GMAIL_IMAP_PORT, timeout=30)
            mail.login(username, password_clean)
            return mail
        except Exception as e:
            last_err = e
            if attempt < 2:
                import time
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"Could not connect to {username} after 3 attempts: {last_err}")


def get_username() -> str:
    accs = get_accounts()
    return accs[0][0] if accs else ""
