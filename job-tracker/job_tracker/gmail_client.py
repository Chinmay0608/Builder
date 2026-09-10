"""
Gmail API search + fetch wrappers.

Features:
- Compound query builder for application signals and response signals
- Full pagination through all matching messages
- On-disk cache keyed by query hash  (./cache/<hash16>.json)
- Exponential backoff on HTTP 429 / 5xx
"""

from __future__ import annotations
import base64
import hashlib
import json
import pathlib
import time

from googleapiclient.errors import HttpError

_CACHE_DIR = pathlib.Path("cache")

# ── Application signal patterns ──────────────────────────────────────────────

APPLICATION_SUBJECTS = [
    "application submitted",
    "application received",
    "thank you for applying",
    "thanks for applying",
    "we received your application",
    "your application has been received",
    "application confirmation",
    "successfully applied",
    "application for",
]

APPLICATION_ATS_DOMAINS = [
    "greenhouse.io", "lever.co", "workday.com", "myworkday.com",
    "icims.com", "smartrecruiters.com", "joinsuperset.com", "jobvite.com",
    "taleo.net", "successfactors.com", "brassring.com", "bamboohr.com",
    "recruitee.com", "ashbyhq.com", "rippling.com", "keka.com",
    "darwinbox.com", "zohorecruit.com", "hire.withgoogle.com",
]

RESPONSE_KEYWORDS = [
    "interview", "next steps", "assessment", "online test",
    "shortlisted", "offer letter", "congratulations", "rejected",
    "unfortunately", "not moving forward", "regret to inform",
    "we have decided", "other candidates", "no longer moving",
    "selected candidates", "pleased to inform",
]


def build_application_query(since: str) -> str:
    """Gmail search string for application confirmation emails.
    'since' in YYYY/MM/DD format (Gmail query format).
    """
    subj = " OR ".join(f'subject:"{s}"' for s in APPLICATION_SUBJECTS)
    ats  = " OR ".join(f"from:{d}" for d in APPLICATION_ATS_DOMAINS)
    return f"({subj} OR {ats}) after:{since}"


def build_response_query(since: str) -> str:
    """Gmail search string for recruiter response emails."""
    kws = " OR ".join(f'"{k}"' for k in RESPONSE_KEYWORDS)
    return f"({kws}) after:{since} in:inbox"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]

def _cache_path(query: str) -> pathlib.Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{_cache_key(query)}.json"

def _load_cache(query: str) -> list[dict] | None:
    p = _cache_path(query)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_cache(query: str, data: list[dict]) -> None:
    _cache_path(query).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── API helpers ───────────────────────────────────────────────────────────────

def _api_call(method, **kwargs):
    """Execute a Gmail API call with exponential backoff on 429/5xx."""
    delay = 1.0
    for attempt in range(5):
        try:
            return method(**kwargs).execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503) and attempt < 4:
                time.sleep(delay); delay *= 2
            else:
                raise

def _search_messages(service, query: str) -> list[dict]:
    results, page_token = [], None
    while True:
        kw = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kw["pageToken"] = page_token
        resp = _api_call(service.users().messages().list, **kw)
        results.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results

def _fetch_message(service, msg_id: str) -> dict:
    return _api_call(service.users().messages().get, userId="me", id=msg_id, format="full")

def _extract_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_body(part)
            if text:
                return text
    return ""

def _parse_message(raw: dict) -> dict:
    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
    return {
        "id":       raw.get("id", ""),
        "threadId": raw.get("threadId", ""),
        "subject":  headers.get("subject", ""),
        "sender":   headers.get("from", ""),
        "to":       headers.get("to", ""),
        "date":     headers.get("date", ""),
        "snippet":  raw.get("snippet", ""),
        "body":     _extract_body(raw.get("payload", {})),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_emails(service, query: str, use_cache: bool = True) -> list[dict]:
    """
    Return parsed messages matching query.
    Each dict: id, threadId, subject, sender, to, date, snippet, body.
    """
    if use_cache:
        cached = _load_cache(query)
        if cached is not None:
            print(f"    [cache] loaded {len(cached)} messages")
            return cached

    stubs = _search_messages(service, query)
    print(f"    [gmail] fetching {len(stubs)} messages...")
    messages = []
    for stub in stubs:
        try:
            messages.append(_parse_message(_fetch_message(service, stub["id"])))
        except HttpError:
            continue

    if use_cache:
        _save_cache(query, messages)
    return messages
