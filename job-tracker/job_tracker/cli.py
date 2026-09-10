"""
job-tracker CLI entry point (Multi-Account IMAP version).

Usage:
    python -m job_tracker.cli [OPTIONS]
    python tracker.py [OPTIONS]

Options:
  --since YYYY-MM-DD    Start date (default: 2025-01-01)
  --email EMAIL         Filter to a specific account in .env
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

from .auth import get_accounts, get_imap_connection
from .gmail_client import fetch_application_emails, fetch_response_emails
from .extract import extract_info, _parse_date
from .classify import classify_response
from .report import print_summary, write_csv, write_html

_STATUS_RANK = {
    "offer": 5, "interview_invited": 4, "assessment_invited": 3,
    "shortlisted": 2, "rejected": 1, "no_response": 0,
}

_PROMOTIONAL_PATTERNS = [
    "dare2compete.news", "unstop.events", "unstop.email", "emails.unstop.com",
    "newsletters-noreply@linkedin.com", "jobalerts-noreply@linkedin.com",
    "digest-novalue@linkedin.com", "internshala.com", "naukri.com/alert",
]


def build_application_records(emails: list[dict], use_llm: bool, account_name: str = "") -> dict[tuple, dict]:
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
                "account":         msg.get("account") or account_name,
                "source_email_id": msg["id"],
            }
    return records


def apply_responses(records: dict, response_emails: list[dict], account_name: str = "") -> None:
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
                    if account_name and account_name not in rec.get("account", ""):
                        rec["account"] = f"{rec.get('account', '')}, {account_name}".strip(", ")
                matched = True
                break

        if not matched:
            info = extract_info(msg, use_llm=False)
            date_str = _parse_date(msg.get("date", ""))
            new_rec = {
                "company":         info.get("company", ""),
                "role":            info.get("role", ""),
                "date_applied":    "",
                "status":          status,
                "last_updated":    date_str,
                "account":         msg.get("account") or account_name,
                "source_email_id": msg["id"],
            }
            record_list.append(new_rec)
            records[(msg["id"],)] = new_rec


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
        description="Analyze your Gmail (IMAP) across all accounts to track job applications.",
    )
    parser.add_argument("--since", default="2025-01-01",
                        help="Start date YYYY-MM-DD (default: 2025-01-01)")
    parser.add_argument("--email", default="",
                        help="Filter to a specific account in .env (substring match)")
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

    all_accounts = get_accounts()
    if not all_accounts:
        print("ERROR: No email accounts found in .env.", file=sys.stderr)
        sys.exit(1)

    if args.email:
        accounts = [a for a in all_accounts if args.email.lower() in a[0].lower()]
        if not accounts:
            print(f"ERROR: No account matching '{args.email}' found in .env.", file=sys.stderr)
            sys.exit(1)
    else:
        accounts = all_accounts

    print(f"\n{'='*62}", flush=True)
    print(f"  JOB TRACKER  --  Multi-Account Scan ({len(accounts)} account(s))", flush=True)
    print(f"  Search period: since {args.since} to {until_iso}", flush=True)
    print(f"{'='*62}", flush=True)
    for i, (usr, _) in enumerate(accounts, 1):
        print(f"  [{i}] {usr}", flush=True)
    print(flush=True)

    aggregated_records: dict[tuple, dict] = {}

    for idx, (username, password) in enumerate(accounts, 1):
        print(f"--- [{idx}/{len(accounts)}] Scanning: {username} ---", flush=True)
        try:
            mail = get_imap_connection(username, password)
        except Exception as e:
            print(f"  [error] Could not connect to {username}: {e}", file=sys.stderr, flush=True)
            continue

        print("  Connected via IMAP!", flush=True)

        # 1. Applications
        app_emails = fetch_application_emails(mail, args.since, account=username, use_cache=use_cache)
        for m in app_emails:
            m["account"] = username
        print(f"  Application emails found: {len(app_emails)}", flush=True)

        # 2. Responses
        resp_emails = fetch_response_emails(mail, args.since, account=username, use_cache=use_cache)
        for m in resp_emails:
            m["account"] = username
        print(f"  Response emails found:    {len(resp_emails)}", flush=True)

        try:
            mail.logout()
        except Exception:
            pass

        print(f"  Processing & classifying records for {username}...", flush=True)
        # Build records for this account
        acc_records = build_application_records(app_emails, use_llm, account_name=username)
        apply_responses(acc_records, resp_emails, account_name=username)

        # Merge into aggregated
        for k, v in acc_records.items():
            if k not in aggregated_records:
                aggregated_records[k] = v
            else:
                existing = aggregated_records[k]
                # Upgrade status if higher priority
                if _STATUS_RANK.get(v["status"], 0) > _STATUS_RANK.get(existing["status"], 0):
                    existing["status"] = v["status"]
                    existing["last_updated"] = v.get("last_updated") or existing["last_updated"]
                # Keep earlier application date
                if not existing.get("date_applied") and v.get("date_applied"):
                    existing["date_applied"] = v["date_applied"]
                # Append account
                if username not in existing.get("account", ""):
                    existing["account"] = f"{existing.get('account', '')}, {username}".strip(", ")
        print()

    final = sorted(aggregated_records.values(), key=lambda x: x.get("date_applied", ""), reverse=True)

    print_summary(final)

    csv_path = write_csv(final, args.since, until_iso)
    print(f"CSV  -> {csv_path}")

    if args.html:
        html_path = write_html(final, args.since, until_iso)
        print(f"HTML -> {html_path}")


if __name__ == "__main__":
    main()
