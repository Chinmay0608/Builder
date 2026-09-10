"""
job-tracker CLI entry point.

Usage:
    python -m job_tracker.cli [OPTIONS]
    job-tracker [OPTIONS]          # if installed via pip

Options:
  --since YYYY-MM-DD    Start date (default: 2025-01-01)
  --email EMAIL         Gmail address (informational only; OAuth picks the account)
  --credentials PATH    Path to credentials.json (default: ./credentials.json)
  --no-cache            Skip reading/writing the disk cache
  --no-llm              Disable Groq LLM fallback for extraction
  --html                Also write an HTML report to ./output/
  --output-dir DIR      Where to write CSV/HTML (default: ./output)
  --help                Show this message
"""

from __future__ import annotations
import argparse
import datetime
import os
import pathlib
import sys

from .auth import build_gmail_service
from .gmail_client import (
    build_application_query,
    build_response_query,
    fetch_emails,
)
from .extract import extract_info
from .classify import classify_response
from .report import print_summary, write_csv, write_html


def _since_to_gmail(date_str: str) -> str:
    """Convert YYYY-MM-DD -> YYYY/MM/DD for Gmail query."""
    return date_str.replace("-", "/")


def _load_dotenv() -> None:
    """Load .env file from CWD or parent dirs (no external deps)."""
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


def build_application_records(
    service,
    since_gmail: str,
    since_iso: str,
    until_iso: str,
    use_cache: bool,
    use_llm: bool,
) -> list[dict]:
    """Fetch application confirmation emails and build record dicts."""
    query = build_application_query(since_gmail)
    print(f"\n[1/2] Fetching application signals...")
    print(f"      Query: {query[:80]}...")
    emails = fetch_emails(service, query, use_cache=use_cache)
    print(f"      Found {len(emails)} email(s).")

    records: dict[str, dict] = {}   # keyed by (company, role) for dedup

    for msg in emails:
        info = extract_info(msg, use_llm=use_llm)
        company = info.get("company", "").strip()
        role    = info.get("role", "").strip()
        date    = info.get("date_applied", "")

        key = (company.lower(), role.lower()) if (company or role) else msg["id"]
        if key not in records:
            records[key] = {
                "company":        company,
                "role":           role,
                "date_applied":   date,
                "status":         "no_response",
                "last_updated":   date,
                "source_email_id": msg["id"],
            }

    return list(records.values())


def apply_responses(
    records: list[dict],
    service,
    since_gmail: str,
    use_cache: bool,
) -> None:
    """Fetch response emails, match to records, update status in-place."""
    query = build_response_query(since_gmail)
    print(f"\n[2/2] Fetching response signals...")
    print(f"      Query: {query[:80]}...")
    responses = fetch_emails(service, query, use_cache=use_cache)
    print(f"      Found {len(responses)} response email(s).")

    # Index records by company name for fast matching
    by_company: dict[str, list[dict]] = {}
    for rec in records:
        cn = rec.get("company", "").lower()
        by_company.setdefault(cn, []).append(rec)

    for msg in responses:
        status = classify_response(msg)
        if status == "no_response":
            continue

        # Try to find a matching application record
        sender_domain = ""
        import re
        m = re.search(r"@([a-z0-9\-]+)\.", msg.get("sender", ""), re.IGNORECASE)
        if m:
            sender_domain = m.group(1).lower()

        matched = False
        for rec in records:
            company_lower = rec.get("company", "").lower()
            if company_lower and (
                company_lower in sender_domain
                or sender_domain in company_lower
                or company_lower in msg.get("subject", "").lower()
            ):
                # Upgrade status if higher priority
                _STATUS_RANK = {
                    "offer": 5, "interview_invited": 4,
                    "assessment_invited": 3, "shortlisted": 2,
                    "rejected": 1, "no_response": 0,
                }
                if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(rec["status"], 0):
                    rec["status"] = status
                    from .extract import _parse_date
                    rec["last_updated"] = _parse_date(msg.get("date", ""))
                matched = True
                break

        if not matched:
            # Response from unknown company — add as standalone record
            from .extract import extract_info, _parse_date
            info = extract_info(msg, use_llm=False)
            date_str = _parse_date(msg.get("date", ""))
            records.append({
                "company":         info.get("company", ""),
                "role":            info.get("role", ""),
                "date_applied":    "",
                "status":          status,
                "last_updated":    date_str,
                "source_email_id": msg["id"],
            })


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        prog="job-tracker",
        description="Analyze your Gmail to track job applications and responses.",
    )
    parser.add_argument("--since", default="2025-01-01",
                        help="Start date YYYY-MM-DD (default: 2025-01-01)")
    parser.add_argument("--email", default="",
                        help="Gmail address (informational only)")
    parser.add_argument("--credentials", default="credentials.json",
                        help="Path to OAuth credentials.json")
    parser.add_argument("--no-cache", action="store_true",
                        help="Bypass disk cache")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable Groq LLM fallback")
    parser.add_argument("--html", action="store_true",
                        help="Generate HTML report in addition to CSV")
    parser.add_argument("--output-dir", default="output",
                        help="Output directory for CSV/HTML (default: output/)")

    args = parser.parse_args()

    # Validate --since
    try:
        datetime.date.fromisoformat(args.since)
    except ValueError:
        print(f"ERROR: --since must be YYYY-MM-DD, got: {args.since!r}", file=sys.stderr)
        sys.exit(1)

    since_gmail = _since_to_gmail(args.since)
    until_iso   = datetime.date.today().isoformat()
    use_cache   = not args.no_cache
    use_llm     = not args.no_llm

    # Override output dir
    import job_tracker.report as _report_mod
    _report_mod._OUTPUT_DIR = pathlib.Path(args.output_dir)

    print(f"\nJob Tracker -- analyzing Gmail since {args.since}")
    if args.email:
        print(f"Account hint: {args.email}")
    print("Authenticating with Gmail API...")

    service = build_gmail_service(args.credentials)
    print("  Authenticated!")

    records = build_application_records(
        service, since_gmail, args.since, until_iso,
        use_cache, use_llm,
    )
    apply_responses(records, service, since_gmail, use_cache)

    # Sort by date_applied desc
    records.sort(key=lambda x: x.get("date_applied", ""), reverse=True)

    # Output
    print_summary(records)
    csv_path = write_csv(records, args.since, until_iso)
    print(f"CSV saved: {csv_path}")

    if args.html:
        html_path = write_html(records, args.since, until_iso)
        print(f"HTML saved: {html_path}")


if __name__ == "__main__":
    main()
