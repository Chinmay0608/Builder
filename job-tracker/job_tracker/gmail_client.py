"""
Gmail search + fetch via IMAP (stdlib imaplib).

Features:
- Builds IMAP SEARCH queries for application signals and response signals
- Fetches full RFC822 message bytes, parses with email.message (stdlib)
- On-disk cache keyed by query hash (./cache/<hash16>.json)
- Handles multi-part MIME, both text/plain and text/html bodies
"""

from __future__ import annotations
import email
import email.header
import email.utils
import hashlib
import imaplib
import json
import pathlib
import re
import time
from email.message import Message

_CACHE_DIR = pathlib.Path("cache")

# ── Application signal patterns (IMAP SEARCH format) ─────────────────────────

APPLICATION_SUBJECT_KEYWORDS = [
    "application submitted",
    "application received",
    "thank you for applying",
    "thanks for applying",
    "we received your application",
    "your application has been received",
    "application confirmation",
    "successfully applied",
]

APPLICATION_ATS_DOMAINS = [
    "greenhouse.io", "lever.co", "workday.com", "myworkday.com",
    "icims.com", "smartrecruiters.com", "joinsuperset.com", "jobvite.com",
    "taleo.net", "successfactors.com", "brassring.com", "bamboohr.com",
    "recruitee.com", "ashbyhq.com", "rippling.com", "keka.com",
    "darwinbox.com", "zohorecruit.com",
]

RESPONSE_KEYWORDS = [
    "interview",
    "assessment",
    "online test",
    "shortlisted",
    "offer letter",
    "unfortunately",
    "not moving forward",
    "regret to inform",
    "other candidates",
    "not selected",
    "pleased to inform",
    "next steps",
]


def _imap_date(iso_date: str) -> str:
    """Convert YYYY-MM-DD to DD-Mon-YYYY for IMAP SEARCH SINCE."""
    import datetime
    d = datetime.date.fromisoformat(iso_date)
    return d.strftime("%d-%b-%Y")


def _build_or_search(*criteria: str) -> str:
    """
    Build nested IMAP OR criteria from a list of criterion strings.
    IMAP OR takes exactly 2 args, so we nest for more than 2.
    """
    items = list(criteria)
    if len(items) == 1:
        return items[0]
    # fold left: OR a (OR b (OR c d))
    result = items[-1]
    for item in reversed(items[:-1]):
        result = f"OR ({item}) ({result})"
    return result


def build_application_query(since_iso: str) -> str:
    """
    IMAP SEARCH string for application confirmation emails.
    Searches INBOX + [Gmail]/Sent for subject keywords OR ATS sender domains.
    Returns the criteria string (without the leading SEARCH keyword).
    """
    since = _imap_date(since_iso)
    subject_crit = [f'SUBJECT "{kw}"' for kw in APPLICATION_SUBJECT_KEYWORDS]
    from_crit    = [f'FROM "{d}"'    for d in APPLICATION_ATS_DOMAINS]
    all_crit = subject_crit + from_crit
    or_block = _build_or_search(*all_crit)
    return f"({or_block}) SINCE {since}"


def build_response_query(since_iso: str) -> str:
    """IMAP SEARCH string for recruiter response emails in INBOX."""
    since = _imap_date(since_iso)
    kw_crit = [f'SUBJECT "{kw}"' for kw in RESPONSE_KEYWORDS]
    or_block = _build_or_search(*kw_crit)
    return f"({or_block}) SINCE {since}"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:16]

def _cache_path(label: str) -> pathlib.Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{_cache_key(label)}.json"

def _load_cache(label: str) -> list[dict] | None:
    p = _cache_path(label)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_cache(label: str, data: list[dict]) -> None:
    _cache_path(label).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── IMAP fetch helpers ────────────────────────────────────────────────────────

def _decode_header_value(raw: str) -> str:
    """Decode RFC2047-encoded header (e.g. =?UTF-8?b?...?=)."""
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_body(msg: Message) -> str:
    """Extract plain-text body from a parsed email.Message."""
    if msg.is_multipart():
        # Prefer text/plain; fall back to text/html (stripped)
        plain = ""
        html  = ""
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not plain:
                payload = part.get_payload(decode=True)
                if payload:
                    plain = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            elif ct == "text/html" and not html:
                payload = part.get_payload(decode=True)
                if payload:
                    raw_html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    # Very light HTML strip
                    html = re.sub(r"<[^>]+>", " ", raw_html)
                    html = re.sub(r"\s+", " ", html).strip()
        return plain or html
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return ""


def _parse_raw_message(uid: str, raw_bytes: bytes) -> dict:
    """Parse raw RFC822 bytes into a structured dict."""
    msg = email.message_from_bytes(raw_bytes)
    subject = _decode_header_value(msg.get("Subject", ""))
    sender  = _decode_header_value(msg.get("From", ""))
    to      = _decode_header_value(msg.get("To", ""))
    date    = msg.get("Date", "")
    body    = _extract_body(msg)
    snippet = body[:200].replace("\n", " ").replace("\r", "").strip()
    return {
        "id":       uid,
        "threadId": uid,   # IMAP has no thread concept; use UID
        "subject":  subject,
        "sender":   sender,
        "to":       to,
        "date":     date,
        "snippet":  snippet,
        "body":     body,
    }


def _search_folder(mail: imaplib.IMAP4_SSL, folder: str, criteria: str) -> list[str]:
    """Select a folder and return matching UIDs. Silently skip missing folders."""
    try:
        status, _ = mail.select(folder, readonly=True)
        if status != "OK":
            return []
        status, data = mail.uid("search", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []
        uids = data[0].decode().split()
        return uids
    except Exception:
        return []


def _fetch_messages(mail: imaplib.IMAP4_SSL, uids: list[str], chunk_size: int = 40) -> list[dict]:
    """Fetch and parse messages in batches using BODY.PEEK[] (leaves messages unread)."""
    messages = []
    for i in range(0, len(uids), chunk_size):
        chunk = uids[i : i + chunk_size]
        uid_str = ",".join(chunk)
        try:
            status, data = mail.uid("fetch", uid_str, "(BODY.PEEK[] UID)")
            if status != "OK" or not data:
                continue
            for item in data:
                if isinstance(item, tuple) and len(item) == 2:
                    header_str = item[0].decode("latin1", errors="ignore")
                    m = re.search(r"UID\s+(\d+)", header_str, re.IGNORECASE)
                    msg_uid = m.group(1) if m else chunk[0]
                    raw_bytes = item[1]
                    messages.append(_parse_raw_message(msg_uid, raw_bytes))
        except Exception:
            # Fallback to single-UID fetch if batch fails
            for uid in chunk:
                try:
                    status, data = mail.uid("fetch", uid, "(BODY.PEEK[] UID)")
                    if status == "OK" and data and isinstance(data[0], tuple):
                        messages.append(_parse_raw_message(uid, data[0][1]))
                except Exception:
                    continue
    return messages


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_emails(
    mail: imaplib.IMAP4_SSL,
    criteria: str,
    folders: list[str],
    cache_label: str,
    use_cache: bool = True,
) -> list[dict]:
    """
    Fetch all emails matching IMAP criteria across given folders.
    Returns list of parsed message dicts.
    """
    if use_cache:
        cached = _load_cache(cache_label)
        if cached is not None:
            print(f"    [cache] {len(cached)} messages loaded")
            return cached

    all_messages: list[dict] = []
    seen_ids: set[str] = set()

    for folder in folders:
        uids = _search_folder(mail, folder, criteria)
        if not uids:
            continue
        print(f"    [imap]  {folder}: {len(uids)} match(es)")
        msgs = _fetch_messages(mail, uids)
        for m in msgs:
            msg_id = m.get("id") or m.get("subject", "")
            if msg_id not in seen_ids:
                seen_ids.add(msg_id)
                all_messages.append(m)

    if use_cache:
        _save_cache(cache_label, all_messages)

    return all_messages


# ── Convenience wrappers used by cli.py ──────────────────────────────────────

APPLICATION_FOLDERS = [
    "INBOX",
]

RESPONSE_FOLDERS = [
    "INBOX",
]

def fetch_application_emails(mail, since_iso: str, use_cache: bool = True) -> list[dict]:
    criteria = build_application_query(since_iso)
    return fetch_emails(mail, criteria, APPLICATION_FOLDERS,
                        cache_label=f"app_{since_iso}", use_cache=use_cache)

def fetch_response_emails(mail, since_iso: str, use_cache: bool = True) -> list[dict]:
    criteria = build_response_query(since_iso)
    return fetch_emails(mail, criteria, RESPONSE_FOLDERS,
                        cache_label=f"resp_{since_iso}", use_cache=use_cache)
