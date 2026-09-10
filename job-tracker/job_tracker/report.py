"""
Output generation: terminal summary, CSV, and optional HTML report.

CSV columns: company, role, date_applied, status, last_updated, source_email_id
"""

from __future__ import annotations
import csv
import datetime
import html
import pathlib
import sys
from typing import Any

from .classify import status_label, STATUS_EMOJI, STATUS_LABELS

_OUTPUT_DIR = pathlib.Path("output")
_STATUS_ORDER = [
    "offer", "interview_invited", "assessment_invited",
    "shortlisted", "rejected", "no_response",
]
_CSV_COLS = ["company", "role", "date_applied", "status", "last_updated", "account", "source_email_id"]


def write_csv(applications: list[dict[str, Any]], since: str, until: str) -> pathlib.Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / f"applications_{since.replace('-','')}_{until.replace('-','')}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(applications)
    return path


def _safe_print(text: str = "") -> None:
    """Print text safely, replacing unencodable characters for current terminal."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


def print_summary(applications: list[dict[str, Any]]) -> None:
    if not applications:
        _safe_print("No applications found.")
        return

    by_status: dict[str, list] = {s: [] for s in _STATUS_ORDER}
    for app in applications:
        by_status.setdefault(app.get("status", "no_response"), []).append(app)

    _safe_print(f"\n{'='*62}")
    _safe_print(f"  JOB APPLICATION TRACKER  --  {len(applications)} application(s) found")
    _safe_print(f"{'='*62}\n")

    for status in _STATUS_ORDER:
        items = by_status.get(status, [])
        if not items:
            continue
        _safe_print(f"{status_label(status)}  ({len(items)})")
        _safe_print("-" * 50)
        for app in sorted(items, key=lambda x: x.get("date_applied", ""), reverse=True):
            company  = app.get("company")  or "Unknown"
            role     = app.get("role")     or "Unknown role"
            date     = app.get("date_applied") or "?"
            updated  = app.get("last_updated")  or ""
            account = app.get("account", "")
            acc_tag = f" ({account.split('@')[0]})" if account else ""
            _safe_print(f"  {date}  {company:<28}  {role}{acc_tag}")
            if updated and updated != date:
                _safe_print(f"               last update: {updated}")
        _safe_print()

    _safe_print(f"{'='*62}")
    _safe_print("  Status breakdown:")
    for status in _STATUS_ORDER:
        count = len(by_status.get(status, []))
        if count:
            bar = "#" * min(count, 25)
            _safe_print(f"  {status_label(status):<30} {bar} {count}")
    _safe_print(f"{'='*62}\n")


# ── HTML report ───────────────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Job Tracker</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1a1a2e}}
  h1{{color:#16213e}}
  .meta{{color:#666;margin-bottom:1.5rem}}
  .cards{{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1.5rem}}
  .card{{padding:.8rem 1.2rem;border-radius:8px;background:#f0f0f0;text-align:center;min-width:90px}}
  .card-n{{font-size:1.8rem;font-weight:700}}
  .card-l{{font-size:.75rem;color:#666}}
  table{{width:100%;border-collapse:collapse;font-size:.9rem}}
  th{{background:#16213e;color:#fff;padding:.6rem .8rem;text-align:left}}
  tr:nth-child(even){{background:#f5f5f5}}
  td{{padding:.5rem .8rem;border-bottom:1px solid #ddd}}
  .badge{{padding:2px 8px;border-radius:12px;font-size:.8rem;font-weight:600}}
  .offer{{background:#d4edda;color:#155724}}
  .interview_invited{{background:#cce5ff;color:#004085}}
  .assessment_invited{{background:#fff3cd;color:#856404}}
  .shortlisted{{background:#d1ecf1;color:#0c5460}}
  .rejected{{background:#f8d7da;color:#721c24}}
  .no_response{{background:#e2e3e5;color:#383d41}}
</style>
</head>
<body>
<h1>&#128203; Job Application Tracker</h1>
<p class="meta">Generated: {generated} | Period: {since} &#8594; {until} | Total: {total}</p>
<div class="cards">{cards}</div>
<table>
<thead><tr><th>Date Applied</th><th>Company</th><th>Role</th><th>Status</th><th>Last Updated</th><th>Account</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""

_CARD = '<div class="card"><div class="card-n">{n}</div><div class="card-l">{l}</div></div>'
_ROW  = ('<tr><td>{d}</td><td>{c}</td><td>{r}</td>'
         '<td><span class="badge {s}">{sl}</span></td><td>{u}</td><td><small>{a}</small></td></tr>')


def write_html(applications: list[dict[str, Any]], since: str, until: str) -> pathlib.Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_status: dict[str, int] = {}
    for app in applications:
        s = app.get("status", "no_response")
        by_status[s] = by_status.get(s, 0) + 1

    cards = "".join(
        _CARD.format(n=by_status.get(s, 0), l=STATUS_LABELS.get(s, s))
        for s in _STATUS_ORDER if by_status.get(s, 0)
    )
    rows = "".join(
        _ROW.format(
            d=html.escape(app.get("date_applied", "")),
            c=html.escape(app.get("company") or "Unknown"),
            r=html.escape(app.get("role") or "Unknown"),
            s=app.get("status", "no_response"),
            sl=html.escape(status_label(app.get("status", "no_response"))),
            u=html.escape(app.get("last_updated", "")),
            a=html.escape(app.get("account", "")),
        )
        for app in sorted(applications, key=lambda x: x.get("date_applied",""), reverse=True)
    )

    content = _HTML.format(
        generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        since=since, until=until, total=len(applications),
        cards=cards, rows=rows,
    )
    path = _OUTPUT_DIR / f"applications_{since.replace('-','')}_{until.replace('-','')}.html"
    path.write_text(content, encoding="utf-8")
    return path
