"""
job-tracker CLI entry point (IMAP version).

Usage:
    python -m job_tracker.cli [OPTIONS]

Options:
  --since YYYY-MM-DD    Start date (default: 2025-01-01)
  --no-cache            Skip disk cache
  --no-llm              Disable Groq LLM fallback
  --html                Also write an HTML report
  --output-dir DIR      Output directory (default: ./output)
  --help                Show this message
"""

from __future__ import annotations
import argparse
import datetime
import pathlib
import re
import sys

from .auth import get_imap_connection, get_username
from .gmail_client import fetch_application_emails, fetch_response_emails
from .extract import extract_info, _parse_date
from .classify import classify_response
from .report import print_summary, write_csv, write_html

_STATUS_RANK = {
    "offer": 5, "interview_invited": 4, "assessment_invited": 3,
    "shortlisted": 2, "rejected": 1, "no_response": 0,
}


def build_application_records(emails: list[dict], use_llm: bool) -> dict[tuple, dict]:
    records: dict[tuple, dict] = {}
    for msg in emails:
        info = extract_info(msg, use_llm=use_llm)
        company = info.get("company", "").strip()
        role    = info.get("role", "").strip()
        date    = info.get("date_applied", "")
        key = (company.lower(), role.lower()) if (company or role) else (msg["id"],)
        if key not in records:
            records[key] = {
                "company":         company,
                "role":            role,
                "date_applied":    date,
                "status":          "no_response",
                "last_updated":    date,
                "source_email_id": msg["id"],
            }
    return records


_PROMOTIONAL_PATTERNS = [
    "dare2compete.news", "unstop.events", "unstop.email", "emails.unstop.com",
    "newsletters-noreply@linkedin.com", "jobalerts-noreply@linkedin.com",
    "digest-novalue@linkedin.com", "internshala.com", "naukri.com/alert",
]


def apply_responses(records: dict, response_emails: list[dict]) -> None:
    record_list = list(records.values())
    for msg in response_emails:
        sender = msg.get("sender", "").lower()
        if any(pat in sender for pat in _PROMOTIONAL_PATTERNS):
            continue

        status = classify_response(msg)
        if status == "no_response":
            continue

        m = re.search(r"@([a-z0-9\-]+)\.", sender, re.IGNORECASE)
        sender_domain = m.group(1).lower() if m else ""
        subject_lower = msg.get("subject", "").lower()

        matched = False
        for rec in record_list:
            company_lower = rec.get("company", "").lower()
            if company_lower and (
                company_lower in sender_domain
                or sender_domain in company_lower
                or company_lower in subject_lower
            ):
                if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(rec["status"], 0):
                    rec["status"] = status
                    rec["last_updated"] = _parse_date(msg.get("date", ""))
                matched = True
                break

        if not matched:
            info = extract_info(msg, use_llm=False)
            date_str = _parse_date(msg.get("date", ""))
            record_list.append({
                "company":         info.get("company", ""),
                "role":            info.get("role", ""),
                "date_applied":    "",
                "status":          status,
                "last_updated":    date_str,
                "source_email_id": msg["id"],
            })
            # add to records dict too
            records[(msg["id"],)] = record_list[-1]


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="job-tracker",
        description="Analyze your Gmail (IMAP) to track job applications.",
    )
    parser.add_argument("--since", default="2025-01-01",
                        help="Start date YYYY-MM-DD (default: 2025-01-01)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Bypass disk cache")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable Groq LLM fallback for extraction")
    parser.add_argument("--html", action="store_true",
                        help="Also generate an HTML report")
    parser.add_argument("--output-dir", default="output",
                        help="Output directory (default: output/)")
    args = parser.parse_args()

    try:
        datetime.date.fromisoformat(args.since)
    except ValueError:
        print(f"ERROR: --since must be YYYY-MM-DD, got: {args.since!r}", file=sys.stderr)
        sys.exit(1)

    until_iso = datetime.date.today().isoformat()
    use_cache = not args.no_cache
    use_llm   = not args.no_llm

    import job_tracker.report as _report_mod
    _report_mod._OUTPUT_DIR = pathlib.Path(args.output_dir)

    username = get_username()
    print(f"\nJob Tracker  |  account: {username or '(from .env)'}  |  since: {args.since}")
    print("Connecting to Gmail via IMAP...")

    try:
        mail = get_imap_connection()
    except Exception as e:
        print(f"\nERROR: Could not connect to Gmail.\n{e}", file=sys.stderr)
        sys.exit(1)

    print("  Connected!\n")

    print("[1/2] Fetching application confirmation emails...")
    app_emails = fetch_application_emails(mail, args.since, use_cache=use_cache)
    print(f"      Total: {len(app_emails)} email(s)\n")

    print("[2/2] Fetching response / recruiter emails...")
    resp_emails = fetch_response_emails(mail, args.since, use_cache=use_cache)
    print(f"      Total: {len(resp_emails)} email(s)\n")

    mail.logout()

    print("Processing...")
    records = build_application_records(app_emails, use_llm)
    apply_responses(records, resp_emails)

    final = sorted(records.values(), key=lambda x: x.get("date_applied", ""), reverse=True)

    print_summary(final)

    csv_path = write_csv(final, args.since, until_iso)
    print(f"CSV  -> {csv_path}")

    if args.html:
        html_path = write_html(final, args.since, until_iso)
        print(f"HTML -> {html_path}")


if __name__ == "__main__":
    main()
