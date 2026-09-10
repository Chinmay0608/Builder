"""
Response-type classifier for incoming recruiter / company emails.

Status tags (priority order, highest wins):
  offer             -> job offer received
  interview_invited -> invited for interview / call
  assessment_invited-> coding test / OA / assignment
  shortlisted       -> shortlisted / selected for next round
  rejected          -> rejection email
  no_response       -> default (no response email found)
"""

from __future__ import annotations
import re

_PATTERNS: dict[str, list[str]] = {
    "offer": [
        r"\boffer\s+letter\b", r"\bextend(?:ing)?\s+an?\s+offer\b",
        r"\bpleased\s+to\s+offer\b", r"\bwelcome\s+aboard\b",
        r"\bstart\s+date\b.*\bjoin\b",
    ],
    "interview_invited": [
        r"\binterview\b", r"\bschedule\s+a\s+call\b", r"\bvideo\s+call\b",
        r"\bphone\s+screen\b", r"\bvirtual\s+interview\b",
        r"\bfinal\s+round\b", r"\btechnical\s+round\b", r"\bhr\s+round\b",
    ],
    "assessment_invited": [
        r"\bonline\s+test\b", r"\bcoding\s+(?:test|challenge|assessment)\b",
        r"\bassessment\b", r"\btest\s+link\b", r"\bhackerrank\b",
        r"\bcodility\b", r"\bhackerearth\b", r"\bcodesignal\b", r"\bamcat\b",
    ],
    "shortlisted": [
        r"\bshortlisted\b",
        r"\bselected\s+for\s+(?:the\s+)?next\s+round\b",
        r"\badvancing\s+to\s+the\s+next\b",
        r"\bwe\s+(?:would\s+)?like\s+to\s+proceed\b",
        r"\bpleased\s+to\s+inform\s+you\b",
        r"\bwe\s+are\s+(?:happy|excited|glad)\s+to\b",
    ],
    "rejected": [
        r"\bregret\b", r"\bunfortunately\b",
        r"\bnot\s+(?:moving|proceeding)\s+forward\b",
        r"\bother\s+candidates\b",
        r"\bwe\s+have\s+decided\s+to\s+(?:move|proceed)\s+with\s+other\b",
        r"\bno\s+longer\s+considering\b", r"\bnot\s+selected\b",
    ],
}

_COMPILED = {
    status: [re.compile(p, re.IGNORECASE | re.DOTALL) for p in pats]
    for status, pats in _PATTERNS.items()
}
_PRIORITY = ["offer", "interview_invited", "assessment_invited", "shortlisted", "rejected"]


def classify_response(msg: dict) -> str:
    """Return a status tag for a response email."""
    text = " ".join([
        msg.get("subject", ""),
        msg.get("snippet", ""),
        msg.get("body", "")[:2000],
    ])
    for status in _PRIORITY:
        for pattern in _COMPILED[status]:
            if pattern.search(text):
                return status
    return "no_response"


STATUS_LABELS = {
    "offer":             "Offer",
    "interview_invited": "Interview",
    "assessment_invited":"Assessment",
    "shortlisted":       "Shortlisted",
    "rejected":          "Rejected",
    "no_response":       "No Response",
}

STATUS_EMOJI = {
    "offer":             "🎉",
    "interview_invited": "📅",
    "assessment_invited":"📝",
    "shortlisted":       "✅",
    "rejected":          "❌",
    "no_response":       "⏳",
}

def status_label(status: str) -> str:
    emoji = STATUS_EMOJI.get(status, "")
    label = STATUS_LABELS.get(status, status)
    return f"{emoji} {label}".strip()
