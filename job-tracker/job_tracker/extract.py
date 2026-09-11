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
    "dydirector", "khushi", "registrar", "tpo", "coordinator", "jecrc",
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
    "honeywell": "Honeywell",
    "oneforma": "OneForma",
    "uber": "Uber",
    "celonis": "Celonis",
    "rubrik": "Rubrik",
    "beyondtrust": "BeyondTrust",
    "veeva": "Veeva Systems",
    "cisco": "Cisco",
    "salesforce": "Salesforce",
    "qualcomm": "Qualcomm",
    "stripe": "Stripe",
    "mastercard": "MasterCard",
    "ea.com": "Electronic Arts",
    "pwc": "PwC",
    "walmart": "Walmart",
    "hp.com": "HP",
    "micro1": "micro1",
    "diversio": "Diversio",
    "taskify": "Taskify AI",
    "goldmansachs": "Goldman Sachs",
    "tcs": "TCS",
    "propvivo": "propVIVO",
    "onebanc": "OneBanc",
    "handshake": "Handshake AI",
    "fi.money": "Fi Money",
    "workloom": "Fi Money",
    "nokia": "Nokia",
    "hpe": "HPE",
    "celebal": "Celebal Technologies",
    "prodesk": "Prodesk IT",
    "magicpin": "Magicpin",
    "gocomet": "GoComet",
    "hcl": "HCLTech",
}

NOISE_SENDERS = [
    "jobalerts-noreply@linkedin.com", "newsletters-noreply@linkedin.com", "digest-novalue@linkedin.com",
    "updates-noreply@linkedin.com", "jobs-noreply@linkedin.com", "linkedin.com",
    "noreply@glassdoor.com", "glassdoor.com", "match.indeed.com", "donotreply@match.indeed.com",
    "codingninjas.com", "internshala.com", "dare2compete.com", "dare2compete.news",
    "unstop.events", "unstop.email",
    "zerodha.com", "qmailer", "angelbroking.in", "groww.in",
    "github.com", "3scale.redhat.com",
    "proteantech.in", "aadhaar", "nic.in",
    "quora.com", "quora-digest", "english-quora-di",
    "jobscan.co", "jobscan.com", "coursiv", "apna.co",
    "leetcode.com", "geeksforgeeks.org", "interviewbit.com", "codingblocks.com",
    "udacity.com", "acciojob.com", "instahyre.com", "naukri.com",
    "dydirector@jecrc.ac.in", "registrar@jecrc.ac.in",
]

_JOB_TITLE_STARTS = (
    "apprentice", "intern", "engineer", "developer", "trainee",
    "associate", "analyst", "specialist", "manager", "lead", "full stack",
    "backend", "frontend", "software",
)

NOISE_SUBJECTS = [
    r"a third-party (?:github|oauth) application",
    r"pan application",
    r"aadhaar application",
    r"ipo application",
    r"applying for ipos",
    r"scam alert",
    r"application forms",
    r"application streak",
    r"application boost",
    r"scholarship",
    r"vip application",
    r"cgl 2022 applied",
    r"explore preparation resources to help you earn a microsoft applied",
    r"microsoft applied learning feedback",
    r"prepare with ai and get hired",
    r"everything you need before your next application",
]

def is_noise_email(msg: dict) -> bool:
    """Return True if email is promotional, digest alert, or non-job related."""
    sender = (msg.get("sender") or "").lower()
    subject = (msg.get("subject") or "").lower()
    if any(n in sender for n in NOISE_SENDERS):
        return True
    if any(re.search(pat, subject) for pat in NOISE_SUBJECTS):
        return True
    if "wellfound.com" in sender and not re.search(r"\b(?:application|applied|submitt|interview|offer|shortlist)\b", subject):
        return True
    return False

_SUPERSET_SUBMIT_PAT = re.compile(
    r"Application submitted(?: by college)?\s*(?:for:?|:)\s*([A-Za-z0-9 .,&!\-]+?)['’]s\s*(.+)",
    re.IGNORECASE,
)
_SUPERSET_OPEN_PAT = re.compile(
    r"(?:\[REMINDER\]\s*)?Open for application\s*-\s*([A-Za-z0-9 .,&!\-]+?)['’]s\s*Job Profile(?:\s*:\s*(.+))?",
    re.IGNORECASE,
)
_MERCOR_SUBMIT_PAT = re.compile(r"Application Submitted\s*-\s*(.+?)(?:\s+on\s+.*)?$", re.IGNORECASE)
_MERCOR_UPDATE_PAT = re.compile(r"Update on your application for\s*(.+)", re.IGNORECASE)
_UIPATH_PAT = re.compile(r"application to UiPath:\s*(.+)", re.IGNORECASE)
_WELLFOUND_PAT = re.compile(r"Application to\s+([A-Za-z0-9 .,&\-]+?)\s+successfully submitted", re.IGNORECASE)
_UNSTOP_PAT = re.compile(r"application for\s+([A-Za-z0-9 .,&\-]+?)\s+is\s+(?:confirmed|submitted)", re.IGNORECASE)
_RECENT_APP_PAT = re.compile(r"recent job application for\s+(?:(?:\d+\s*-\s*)?([A-Za-z0-9 .,&\-\(\)]+))", re.IGNORECASE)
_INDEED_APPLY_PAT = re.compile(r"Indeed Application:\s*(.+)", re.IGNORECASE)

_COMPANY_SUBJECT_PATTERNS = [
    re.compile(r"(?:application\s+(?:for\s+.+?\s+at|to)|applied\s+to|applying\s+to)\s+([A-Z][A-Za-z0-9 &,.\-]+)", re.IGNORECASE),
    re.compile(r"Confirming\s+your\s+([A-Za-z0-9 &.\-]+?)\s+job\s+application", re.IGNORECASE),
    re.compile(r"([A-Za-z0-9 &.\-]+?)\s+Application:", re.IGNORECASE),
    re.compile(r"Your\s+application\s+to\s+([A-Za-z0-9 &.\-]+?)(?:\s*[\(!\-–]|$)", re.IGNORECASE),
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

    # Check known domains in address first (e.g. mail.amazon.jobs -> Amazon, americanexpress -> American Express)
    addr_lower = addr.lower()
    for key, val in _KNOWN_DOMAINS.items():
        if key in addr_lower:
            return val

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

    # Check display name if clean (e.g. "Stripe", "Haize Labs", "Amex Careers")
    if display_name:
        clean_name = re.sub(r"\s*(?:Careers|Recruiting|Jobs|Talent|Team|Notifications|Events|HR|People Services)\s*", " ", display_name, flags=re.IGNORECASE).strip()
        clean_name = re.sub(r"^Workday\s+", "", clean_name, flags=re.IGNORECASE).strip()
        if clean_name and clean_name.lower() not in _GENERIC_DOMAINS and len(clean_name) > 1:
            return clean_name

    m2 = re.search(r"@([a-z0-9\-]+)\.[a-z]{2,}", addr, re.IGNORECASE)
    if m2:
        domain = m2.group(1).lower()
        if domain not in _GENERIC_DOMAINS:
            return domain.replace("-", " ").title()
    return ""


def _company_from_subject(subject: str) -> str:
    # Superset patterns
    m_sup = _SUPERSET_SUBMIT_PAT.search(subject)
    if m_sup:
        return m_sup.group(1).strip()
    m_open = _SUPERSET_OPEN_PAT.search(subject)
    if m_open:
        return m_open.group(1).strip()

    # Mercor
    if re.search(r"(?:mercor|cincinnatus)", subject, re.IGNORECASE):
        return "Mercor"

    # UiPath
    if _UIPATH_PAT.search(subject):
        return "UiPath"

    # Wellfound
    m_wf = _WELLFOUND_PAT.search(subject)
    if m_wf:
        return m_wf.group(1).strip()

    # Unstop
    if _UNSTOP_PAT.search(subject):
        return "Unstop"

    for pat in _COMPANY_SUBJECT_PATTERNS:
        m = pat.search(subject)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"[\s!.,\-]+$", "", val)
            val_low = val.lower()
            if any(val_low.startswith(p) for p in _JOB_TITLE_STARTS):
                continue
            if val_low not in {"the", "a", "an", "your", "position", "role", "job", "opportunity"}:
                return val

    sub_lower = subject.lower()
    for key, val in _KNOWN_DOMAINS.items():
        if len(key) >= 3 and re.search(r"\b" + re.escape(key) + r"\b", sub_lower):
            return val
    return ""


def _role_from_subject(subject: str) -> str:
    # Superset patterns
    m_sup = _SUPERSET_SUBMIT_PAT.search(subject)
    if m_sup:
        return m_sup.group(2).strip()
    m_open = _SUPERSET_OPEN_PAT.search(subject)
    if m_open and m_open.group(2):
        return m_open.group(2).strip()

    # Indeed Apply
    m_ind = _INDEED_APPLY_PAT.search(subject)
    if m_ind:
        return m_ind.group(1).strip()

    # Mercor
    m_mer = _MERCOR_SUBMIT_PAT.search(subject) or _MERCOR_UPDATE_PAT.search(subject)
    if m_mer:
        return m_mer.group(1).strip()

    # UiPath
    m_ui = _UIPATH_PAT.search(subject)
    if m_ui:
        return m_ui.group(1).strip()

    # Unstop
    m_un = _UNSTOP_PAT.search(subject)
    if m_un:
        return m_un.group(1).strip()

    # Recent job application for
    m_rec = _RECENT_APP_PAT.search(subject)
    if m_rec:
        return m_rec.group(1).strip()

    # If subject had "applying to <Role>", capture role here
    for pat in _COMPANY_SUBJECT_PATTERNS:
        m = pat.search(subject)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"[\s!.,\-]+$", "", val)
            val_low = val.lower()
            if any(val_low.startswith(p) for p in _JOB_TITLE_STARTS):
                return val

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
    m = re.search(r" (\d{4}-\d{2}-\d{2}) ", date_str)
    return m.group(1) if m else date_str[:10]


def extract_rule_based(msg: dict) -> dict:
    subject = msg.get("subject", "")
    sender  = msg.get("sender", "")
    company = _company_from_subject(subject)
    if not company:
        company = _company_from_sender(sender)
    role = _role_from_subject(subject)
    if "indeedapply" in sender.lower() or "indeed application:" in subject.lower():
        if not company or company == "Indeed":
            company = "Indeed Apply"
    if company:
        company = re.sub(r"\s*(?:Careers|Recruiting|Jobs|Talent|Team|Notifications|Events|HR|People Services)$", "", company, flags=re.IGNORECASE).strip()
        company = re.sub(r"[\s!.,\-]+$", "", company).strip()
    return {
        "company":      company,
        "role":         role,
        "date_applied": _parse_date(msg.get("date", "")),
    }


# ── Groq LLM fallback ─────────────────────────────────────────────────────────

_GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "qwen/qwen3.6-27b"]

_SYSTEM_PROMPT = (
    "You are a precise information extractor. Given an email subject, sender, and snippet, "
    "extract: company (string, clean corporate name, title-case), role (job title/position, or empty string if not found), "
    "and date_applied (YYYY-MM-DD). "
    'Respond ONLY with a valid JSON object: {"company": "...", "role": "...", "date_applied": "YYYY-MM-DD"}. '
    'Use empty string "" for unknown fields. No markdown, no explanation.'
)

_ACTIVE_KEY_INDEX = 0


def _get_groq_api_keys() -> list[str]:
    """Discover all Groq API keys configured in .env or environment variables."""
    _load_dotenv()
    keys: list[str] = []
    for k, v in os.environ.items():
        if k == "GROQ_API_KEY" or k.startswith("GROQ_API_KEY_") or k == "GROQ_API_KEYS":
            for part in v.replace(";", ",").split(","):
                clean = part.strip().strip("'\"")
                if clean and clean not in keys:
                    keys.append(clean)
    return keys


def _call_groq(subject: str, sender: str, snippet: str, body: str = "") -> dict:
    global _ACTIVE_KEY_INDEX
    keys_pool = _get_groq_api_keys()
    if not keys_pool:
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

        num_keys = len(keys_pool)
        for offset in range(num_keys):
            k_idx = (_ACTIVE_KEY_INDEX + offset) % num_keys
            curr_key = keys_pool[k_idx]

            req = urllib.request.Request(
                _GROQ_URL,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {curr_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                },
            )

            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        text = resp_data["choices"][0]["message"]["content"].strip()
                        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            _ACTIVE_KEY_INDEX = k_idx
                            return parsed
                except urllib.error.HTTPError as e:
                    # Smart shift to next key on rate limit (429) or quota / auth error
                    if e.code in (429, 401, 402):
                        _ACTIVE_KEY_INDEX = (k_idx + 1) % num_keys
                        break
                    if e.code in (500, 502, 503, 504) and attempt < 1:
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
