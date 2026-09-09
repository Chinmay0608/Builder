#!/usr/bin/env python3
"""
job_toolkit/tracker.py — CLI Application Tracker stored in applications.json.

Commands:
  python tracker.py add      # Add a new application
  python tracker.py list     # List all applications in a clean table
  python tracker.py update   # Update the status/notes of an application
  python tracker.py stats    # View summary application statistics
"""

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, List

# Reconfigure stdout/stderr to UTF-8 for cross-platform and Windows terminal support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APPLICATIONS_FILE = os.path.join(SCRIPT_DIR, "applications.json")

VALID_STATUSES = [
    "Applied",
    "OA Sent",
    "Interview Scheduled",
    "Offer",
    "Rejected",
    "No Reply",
]


def load_applications() -> List[Dict[str, Any]]:
    """Loads all applications from applications.json."""
    if not os.path.isfile(APPLICATIONS_FILE):
        return []
    try:
        with open(APPLICATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[warn] Failed to read {APPLICATIONS_FILE}: {e}", file=sys.stderr)
        return []


def save_applications(apps: List[Dict[str, Any]]) -> None:
    """Saves applications to applications.json."""
    try:
        with open(APPLICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(apps, f, indent=2)
    except OSError as e:
        sys.exit(f"[error] Failed to save applications: {e}")


def add_application(
    company: str = "",
    role: str = "",
    status: str = "Applied",
    resume_version: str = "",
    notes: str = "",
    apply_link: str = "",
) -> Dict[str, Any]:
    """Adds a new application interactively or programmatically."""
    today = datetime.date.today().isoformat()

    if not company:
        company = input("Company name: ").strip()
        while not company:
            company = input("Company name (required): ").strip()

    if not role:
        role = input("Role / Position: ").strip() or "Software Engineer"

    if not status or status not in VALID_STATUSES:
        print("\nSelect Status:")
        for idx, s in enumerate(VALID_STATUSES, 1):
            print(f"  {idx}. {s}")
        choice = input(f"Choice [default 1 ({VALID_STATUSES[0]})]: ").strip()
        try:
            status = VALID_STATUSES[int(choice) - 1] if choice else VALID_STATUSES[0]
        except (ValueError, IndexError):
            status = VALID_STATUSES[0]

    if not resume_version:
        resume_version = input("Resume used / version [e.g. full_stack, Chinmay_Resume_Google.tex]: ").strip()

    if not apply_link:
        apply_link = input("Job posting / Application URL (optional): ").strip()

    if not notes:
        notes = input("Notes / Referral info (optional): ").strip()

    app_entry = {
        "company": company,
        "role": role,
        "date_applied": today,
        "status": status,
        "resume_version": resume_version,
        "notes": notes,
        "apply_link": apply_link,
    }

    apps = load_applications()
    apps.append(app_entry)
    save_applications(apps)

    print(f"\n✅ Application for {company} ({role}) logged successfully.")
    return app_entry


def list_applications() -> None:
    """Displays all tracked applications in a clean, formatted table."""
    apps = load_applications()
    if not apps:
        print("\nNo applications tracked yet. Run 'python tracker.py add' to log your first one!\n")
        return

    print("\n" + "=" * 78)
    print(f"{'#':<3}  {'Company':<20} {'Role':<26} {'Status':<16} {'Date':<10}")
    print("─" * 78)

    for i, app in enumerate(apps, 1):
        comp = (app.get("company") or "Unknown")[:19]
        role = (app.get("role") or "Unknown")[:25]
        status = (app.get("status") or "Applied")[:15]
        date_str = (app.get("date_applied") or "")[:10]
        print(f"{i:<3}  {comp:<20} {role:<26} {status:<16} {date_str:<10}")

    print("=" * 78 + "\n")


def update_application() -> None:
    """Interactively updates the status and notes of an application."""
    apps = load_applications()
    if not apps:
        print("\nNo applications to update. Run 'python tracker.py add' first.\n")
        return

    list_applications()
    idx_input = input(f"Enter application number to update (1-{len(apps)}): ").strip()
    try:
        idx = int(idx_input) - 1
        if idx < 0 or idx >= len(apps):
            raise ValueError
    except ValueError:
        print("[error] Invalid application number.")
        return

    app = apps[idx]
    print(f"\nUpdating application: {app.get('company')} — {app.get('role')}")
    print(f"Current Status : {app.get('status')}")
    print(f"Current Notes  : {app.get('notes', 'None')}\n")

    print("Select new status:")
    for i, s in enumerate(VALID_STATUSES, 1):
        marker = " (current)" if s == app.get("status") else ""
        print(f"  {i}. {s}{marker}")

    s_choice = input("Enter status choice (or press Enter to keep current): ").strip()
    if s_choice:
        try:
            app["status"] = VALID_STATUSES[int(s_choice) - 1]
        except (ValueError, IndexError):
            print("[warn] Invalid choice. Keeping current status.")

    new_notes = input(f"New notes (press Enter to keep '{app.get('notes', '')}'): ").strip()
    if new_notes:
        app["notes"] = new_notes

    save_applications(apps)
    print(f"\n✅ Application #{idx + 1} ({app.get('company')}) updated to '{app.get('status')}'.\n")


def show_stats() -> None:
    """Calculates and prints application response statistics."""
    apps = load_applications()
    total = len(apps)

    if total == 0:
        print("\nNo applications found. Add applications to see response statistics.\n")
        return

    applied_count = sum(1 for a in apps if a.get("status") == "Applied")
    oa_interview_count = sum(1 for a in apps if a.get("status") in ("OA Sent", "Interview Scheduled", "Offer"))
    rejected_count = sum(1 for a in apps if a.get("status") == "Rejected")
    no_reply_count = sum(1 for a in apps if a.get("status") == "No Reply")

    # Responses received = OA, Interview, Offer, Rejected
    replied_count = oa_interview_count + rejected_count
    reply_rate = (replied_count / total) * 100 if total > 0 else 0.0

    print("\n" + "═" * 38)
    print("       APPLICATION STATISTICS")
    print("═" * 38)
    print(f"Total applications : {total}")
    print(f"Applied            : {applied_count}")
    print(f"OA/Interview       : {oa_interview_count}")
    print(f"Rejected           : {rejected_count}")
    print(f"No Reply           : {no_reply_count}")
    print(f"Reply rate         : {reply_rate:.1f}%")
    print("═" * 38 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Chinmay's Job Application Tracker")
    subparsers = parser.add_subparsers(dest="command", help="Tracker command to run")

    subparsers.add_parser("add", help="Add a new job application")
    subparsers.add_parser("list", help="List all tracked applications")
    subparsers.add_parser("update", help="Update the status of an application")
    subparsers.add_parser("stats", help="Show application stats and reply rate")

    args = parser.parse_args()

    if args.command == "add":
        add_application()
    elif args.command == "list":
        list_applications()
    elif args.command == "update":
        update_application()
    elif args.command == "stats":
        show_stats()
    else:
        # Default to list if no command provided
        list_applications()


if __name__ == "__main__":
    main()
