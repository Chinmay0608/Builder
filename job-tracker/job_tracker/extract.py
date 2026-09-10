"""
Company, role, and date extraction from email messages.

Strategy (rule-based first, Groq LLM fallback when fields are missing):
  1. Regex + known ATS domain patterns (zero API cost).
  2. Groq LLM — only when company or role are blank AND GROQ_API_KEY is set.
"""

from __future__ import annotations
import email.utils
import json
import os
import pathlib
import re
import time
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

# ── Load .env ─────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
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

_load_dotenv()

# ── ATS sender regex ──────────────────────────────────────────────────────────

_ATS_SUBDOMAIN_RE = re.compile(
    r"@([a-z0-9\-]+)\."
    r"(?:greenhouse\.io|lever\.co|icims\.com"
    r"|smartrecruiters\.com|jobvite\.com|taleo\.net|bamboohr\.com|ashbyhq\.com|rippling\.com)",
    re.IGNORECASE,
)

_GENERIC_DOMAINS = {
    "gmail", "yahoo", "outlook", "hotmail", "noreply", "no-reply",
    "mail", "mailer", "notifications", "careers", "jobs", "hr",
    "info", "support", "contact", "donotreply", "recruitment", "talent",
    "news", "events", "email",
}

_KNOWN_DOMAINS = {
    "amazon": "Amazon",
    "google": "Google",
    "microsoft": "Microsoft",
    "joinsuperset": "Superset",
    "razorpay": "Razorpay",
    "americanexpress": "American Express",
    "wellsfargo": "Wells Fargo",
    "binance": "Binance",
    "uipath": "UiPath",
    "bendingspoons": "Bending Spoons",
    "mercor": "Mercor",
    "haizelabs": "Haize Labs",
    "oracle": "Oracle",
}

_COMPANY_SUBJECT_PATTERNS = [
    re.compile(r"(?:application\s+(?:for\s+.+?\s+at|to)|applied\s+to|applying\s+to)\s+([A-Z][A-Za-z0-9 &,.\-]+)", re.IGNORECASE),
    re.compile(r"Confirming\s+your\s+([A-Za-z0-9 &.\-]+?)\s+job\s+application", re.IGNORECASE),
    re.compile(r"([A-Za-z0-9 &.\-]+?)\s+Application:", re.IGNORECASE),
    re.compile(r"Your\s+application\s+to\s+([A-Za-z0-9 &.\-]+?)(?:\s*\(|$)", re.IGNORECASE),
]

_ROLE_SUBJECT_PATTERNS = [
    re.compile(r"(?:position|role|job|opening|opportunity)\s*(?:of|:)?\s*['\"]?([A-Z][A-Za-z0-9 ,\-\(\)]+?)['\"]?(?:\s+at|\s+with|\s*[,\-]|\s*$)", re.IGNORECASE),
    re.compile(r"(?:application(?:\s+(?:received|submitted|confirmed|for))?|applied)\s+for\s+(?:the\s+)?([A-Za-z0-9 ,\-\(\)]+?)(?:\s+(?:at|Position|role)|\s*$)", re.IGNORECASE),
    re.compile(r"Regarding\s+Requisition\s+(?:College\s+)?([A-Za-z0-9 ,\-\(\)]+)", re.IGNORECASE),
]


def _company_from_sender(sender: str) -> str:
    if not sender:
        return ""
    display_name, addr = email.utils.parseaddr(sender)

    # Check display name first if clean (e.g. "Amex Careers" -> "Amex", "Stripe", "PwC")
    if display_name:
        clean_name = re.sub(r"(Careers|Recruiting|Jobs|Talent|Team|Notifications|Events|HR)", "", display_name, flags=re.IGNORECASE).strip()
        clean_name = re.sub(r"^Workday\s+", "", clean_name, flags=re.IGNORECASE).strip()
        if clean_name and clean_name.lower() not in _GENERIC_DOMAINS and len(clean_name) > 1:
            return clean_name

    # Check workday localpart: pwc@myworkday.com -> PwC, hp@myworkday.com -> HP
    m_workday = re.search(r"([a-z0-9\-]+)@(?:[a-z0-9\-]+\.)?myworkday(?:jobs)?\.com", addr, re.IGNORECASE)
    if m_workday:
        co = m_workday.group(1).lower()
        if co not in _GENERIC_DOMAINS:
            return co.upper() if len(co) <= 3 else co.title()

    # Subdomain ATS: noreply@stripe.greenhouse.io -> Stripe
    m = _ATS_SUBDOMAIN_RE.search(addr)
    if m:
        return m.group(1).replace("-", " ").title()

    # Check known domains in address (e.g. mail.amazon.jobs -> Amazon)
    addr_lower = addr.lower()
    for key, val in _KNOWN_DOMAINS.items():
        if key in addr_lower:
            return val

    m2 = re.search(r"@([a-z0-9\-]+)\.[a-z]{2,}", addr, re.IGNORECASE)
    if m2:
        domain = m2.group(1).lower()
        if domain not in _GENERIC_DOMAINS:
            return domain.replace("-", " ").title()
    return ""


def _company_from_subject(subject: str) -> str:
    for pat in _COMPANY_SUBJECT_PATTERNS:
        m = pat.search(subject)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"[\s!.,\-]+$", "", val)
            if val and val.lower() not in {"the", "a", "an", "your"}:
                return val
    return ""


def _role_from_subject(subject: str) -> str:
    for pat in _ROLE_SUBJECT_PATTERNS:
        m = pat.search(subject)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"[\s!.,\-]+$", "", val)
            if val and len(val) > 2:
                return val
    return ""


def _parse_date(date_str: str) -> str:
    try:
        return parsedate_to_datetime(date_str).date().isoformat()
    except Exception:
        pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
    return m.group(1) if m else date_str[:10]


def extract_rule_based(msg: dict) -> dict:
    company = _company_from_subject(msg.get("subject", ""))
    if not company:
        company = _company_from_sender(msg.get("sender", ""))
    role = _role_from_subject(msg.get("subject", ""))
    return {
        "company":      company,
        "role":         role,
        "date_applied": _parse_date(msg.get("date", "")),
    }


# ── Groq LLM fallback ─────────────────────────────────────────────────────────

_GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODELS = ["qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]

_SYSTEM_PROMPT = (
    "You are a precise information extractor. Given an email subject, sender, and snippet, "
    "extract: company (string, clean corporate name, title-case), role (job title/position, or empty string if not found), "
    "and date_applied (YYYY-MM-DD). "
    'Respond ONLY with a valid JSON object: {"company": "...", "role": "...", "date_applied": "YYYY-MM-DD"}. '
    'Use empty string "" for unknown fields. No markdown, no explanation.'
)


def _call_groq(subject: str, sender: str, snippet: str, body: str = "") -> dict:
    _load_dotenv()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {}

    context = (snippet or body)[:600]
    user_msg = f"Subject: {subject}\nFrom: {sender}\nContent: {context}"

    for model in _GROQ_MODELS:
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            "temperature": 0,
            "max_tokens": 100,
        }).encode()

        req = urllib.request.Request(
            _GROQ_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
        )

        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    text = resp_data["choices"][0]["message"]["content"].strip()
                    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 1:
                    time.sleep(1.0)
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
        llm = _call_groq(
            msg.get("subject", ""),
            msg.get("sender", ""),
            msg.get("snippet", ""),
            msg.get("body", ""),
        )
        if llm:
            if not result["company"] and llm.get("company"):
                result["company"] = llm["company"]
            if not result["role"] and llm.get("role"):
                result["role"] = llm["role"]
            if not result["date_applied"] and llm.get("date_applied"):
                result["date_applied"] = llm["date_applied"]
    return result
