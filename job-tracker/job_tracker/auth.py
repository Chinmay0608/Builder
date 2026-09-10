"""
OAuth2 authentication for Gmail API.

First run:  opens a browser for consent, caches token at ~/.job_tracker/token.json
Subsequent: loads cached token, refreshes silently if expired.

Setup steps (one-time):
  1. Go to https://console.cloud.google.com/
  2. Create / select a project.
  3. Enable "Gmail API"  (APIs & Services -> Library).
  4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
       Application type: Desktop app
       Download the JSON -> save as credentials.json in this directory
       (or pass its path with --credentials).
  5. OAuth consent screen -> add your Gmail address as a Test User.
"""

from __future__ import annotations
import os
import pathlib

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_TOKEN_DIR  = pathlib.Path.home() / ".job_tracker"
_TOKEN_PATH = _TOKEN_DIR / "token.json"


def get_credentials(credentials_path: str | pathlib.Path = "credentials.json") -> Credentials:
    """
    Return valid Gmail OAuth2 credentials.
    Loads from cache if available; triggers browser consent flow otherwise.
    Token is persisted to ~/.job_tracker/token.json (mode 0600).
    """
    credentials_path = pathlib.Path(credentials_path)
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {str(credentials_path)!r}.\n"
            "Follow the setup steps in auth.py to create one via Google Cloud Console."
        )

    creds: Credentials | None = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        token_data = creds.to_json()
        fd = os.open(str(_TOKEN_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, token_data.encode())
        finally:
            os.close(fd)

    return creds


def build_gmail_service(credentials_path: str | pathlib.Path = "credentials.json"):
    """Return an authorised Gmail API service object."""
    creds = get_credentials(credentials_path)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
