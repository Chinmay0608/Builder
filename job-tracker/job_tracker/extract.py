"""
Company, role, and date extraction from email messages.

Strategy (rule-based first, Groq LLM fallback when fields are missing):
  1. Regex + known ATS domain patterns (zero API cost).
  2. Groq LLM — only when company or role are blank AND GROQ_API_KEY is set.
"""

from __future__ import annotations
import json
import os
import re
import time
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

# ── ATS sender regex ──────────────────────────────────────────────────────────

_ATS_SUBDOMAIN_RE = re.compile(
    r"@([a-z0-9\-]+)\."
    r"(?:greenhouse\.io|lever\.co|workday\.com|myworkday\.com|icims\.com"
    r"|smartrecruiters\.com|jobvite\.com|taleo\.net|bamboohr\.com|ashbyhq\.com)",
    re.IGNORECASE,
)

_GENERIC_DOMAINS = {
    "gmail", "yahoo", "outlook", "hotmail", "noreply", "no-reply",
    "mail", "mailer", "notifications", "careers", "jobs", "hr",
    "info", "support", "contact", "donotreply",
}

_COMPANY_AT_RE = re.compile(
    r"application\s+(?:for\s+.+?\s+at|to)\s+([A-Z][A-Za-z0-9 &,.\-]+)",
    re.IGNORECASE,
)

_ROLE_RE = re.compile(
    r"(?:position|role|job|opening|opportunity)\s*(?:of|:)?\s*[\"']?"
    r"([A-Z][A-Za-z0-9 ,\-\(\)]+?)[\"']?(?:\s+at|\s+with|\s*[,\-]|\s*$)",
    re.IGNORECASE,
)

_APPLIED_FOR_RE = re.compile(
    r"(?:application(?:\s+(?:received|submitted|confirmed|for))?|applied)\s+for\s+(.+?)(?:\s+at|\s*$)",
    re.IGNORECASE,
)


def _company_from_sender(sender: str) -> str:
    m = _ATS_SUBDOMAIN_RE.search(sender)
    if m:
        return m.group(1).replace("-", " ").title()
    m2 = re.search(r"@([a-z0-9\-]+)\.[a-z]{2,}", sender, re.IGNORECASE)
    if m2:
        domain = m2.group(1).lower()
        if domain not in _GENERIC_DOMAINS:
            return domain.replace("-", " ").title()
    return ""

def _company_from_subject(subject: str) -> str:
    m = _COMPANY_AT_RE.search(subject)
    return m.group(1).strip() if m else ""

def _role_from_subject(subject: str) -> str:
    m = _ROLE_RE.search(subject)
    if m:
        return m.group(1).strip()
    m2 = _APPLIED_FOR_RE.search(subject)
    return m2.group(1).strip() if m2 else ""

def _parse_date(date_str: str) -> str:
    try:
        return parsedate_to_datetime(date_str).date().isoformat()
    except Exception:
        pass
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", date_str)
    return m.group(1) if m else date_str[:10]

def extract_rule_based(msg: dict) -> dict:
    company = _company_from_subject(msg.get("subject", ""))
    if not company:
        company = _company_from_sender(msg.get("sender", ""))
    return {
        "company":      company,
        "role":         _role_from_subject(msg.get("subject", "")),
        "date_applied": _parse_date(msg.get("date", "")),
    }


# ── Groq LLM fallback ─────────────────────────────────────────────────────────

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"
_SYSTEM_PROMPT = (
    "You are a precise information extractor. Given an email subject, sender, and snippet, "
    "extract: company (string, title-case), role (job title), date_applied (YYYY-MM-DD). "
    "Respond ONLY with valid JSON: {\"company\": \"...\", \"role\": \"...\", \"date_applied\": \"YYYY-MM-DD\"}. "
    "Use empty string \"\" for unknown fields. No markdown, no explanation."
)

def _call_groq(subject: str, sender: str, snippet: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {}
    user_msg = f"Subject: {subject}\nFrom: {sender}\nSnippet: {snippet[:400]}"
    payload = json.dumps({
        "model": _GROQ_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0, "max_tokens": 96,
    }).encode()
    req = urllib.request.Request(
        _GROQ_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    delay = 1.0
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
                text = body["choices"][0]["message"]["content"].strip()
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
                return json.loads(text)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(delay); delay *= 2
            else:
                break
        except Exception:
            break
    return {}


# ── Public API ────────────────────────────────────────────────────────────────

def extract_info(msg: dict, use_llm: bool = True) -> dict:
    """Extract company, role, date_applied from a message dict."""
    result = extract_rule_based(msg)
    if use_llm and (not result["company"] or not result["role"]):
        llm = _call_groq(msg.get("subject",""), msg.get("sender",""), msg.get("snippet",""))
        if llm:
            if not result["company"]: result["company"] = llm.get("company", "")
            if not result["role"]:    result["role"]    = llm.get("role", "")
            if not result["date_applied"]: result["date_applied"] = llm.get("date_applied", "")
    return result
