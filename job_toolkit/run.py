#!/usr/bin/env python3
"""
job_toolkit/run.py — Main Interactive Menu for Chinmay's Job Application Toolkit.

Features:
  1. Evaluate a JD (quick verdict, blocker check, stack score)
  2. Tailor resume for a JD (Claude API LaTeX generator)
  3. Evaluate + Tailor (integrated workflow)
  4. Track application (log new application)
  5. View application stats (stats & response rates)
  6. Exit
"""

import os
import sys

# Reconfigure stdout/stderr to UTF-8 for cross-platform and Windows terminal support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure local imports work cleanly
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from evaluate import evaluate_jd, load_profile, read_jd_input
from tailor import tailor_resume
from tracker import add_application, list_applications, show_stats, update_application


def menu_evaluate(profile):
    print("\n--- Evaluate Job Description ---")
    jd_text = read_jd_input()
    if not jd_text or len(jd_text.strip()) < 20:
        print("[warn] Job description empty or too short. Returning to menu.")
        return None
    res = evaluate_jd(jd_text, profile)
    print("\n" + res["report"] + "\n")
    return res, jd_text


def menu_tailor(profile, prefill_jd=None, prefill_company=None, prefill_version=None):
    print("\n--- Tailor LaTeX Resume ---")
    if prefill_jd:
        jd_text = prefill_jd
    else:
        jd_text = read_jd_input()

    if not jd_text or len(jd_text.strip()) < 20:
        print("[warn] Job description empty or too short. Returning to menu.")
        return

    company = prefill_company
    if not company:
        c_in = input("Target Company Name (press Enter to auto-detect): ").strip()
        company = c_in if c_in else None

    version = prefill_version
    if not version:
        print("\nAvailable resume versions:")
        for k, v in profile.get("resume_versions", {}).items():
            print(f"  - {k:14}: {v}")
        user_v = input("\nChoose version (press Enter to auto-detect): ").strip()
        version = user_v if user_v in profile.get("resume_versions", {}) else None

    out_path = tailor_resume(
        jd_text=jd_text,
        resume_version=version,
        company_name=company,
        profile=profile,
    )

    # Offer to track immediately
    track_prompt = input("Log this application in your tracker now? [Y/n]: ").strip().lower()
    if track_prompt in ("", "y", "yes"):
        out_filename = os.path.basename(out_path) if out_path else ""
        add_application(
            company=company or "Company",
            role="Software Engineer",
            status="Applied",
            resume_version=out_filename,
        )


def menu_evaluate_and_tailor(profile):
    print("\n--- Evaluate + Tailor Integrated Workflow ---")
    eval_result = menu_evaluate(profile)
    if not eval_result:
        return

    res, jd_text = eval_result
    verdict = res.get("verdict", "")

    if "SKIP" in verdict:
        print(f"[Notice] The evaluator recommends SKIP: {res.get('action')}")
        proceed = input("Do you still want to generate a tailored resume? [y/N]: ").strip().lower()
        if proceed not in ("y", "yes"):
            print("Skipped tailoring as advised.\n")
            return

    # Automatically pass inferred company and recommended version
    company = res.get("company")
    if company == "Unknown":
        company = input("Enter Company Name: ").strip() or "Company"

    rec_version = res.get("resume_version", "general")
    print(f"\nProceeding to tailor resume using detected version: '{rec_version}' for '{company}'.")

    menu_tailor(
        profile=profile,
        prefill_jd=jd_text,
        prefill_company=company,
        prefill_version=rec_version,
    )


def menu_track():
    print("\n--- Track Applications ---")
    print("1. Add new application")
    print("2. List all applications")
    print("3. Update existing application")
    sub = input("Choose [1-3, default 1]: ").strip()
    if sub == "2":
        list_applications()
    elif sub == "3":
        update_application()
    else:
        add_application()


def main():
    profile = load_profile()

    while True:
        print("═" * 39)
        print("  CHINMAY'S JOB TOOLKIT")
        print("═" * 39)
        print("  1. Evaluate a JD")
        print("  2. Tailor resume for a JD")
        print("  3. Evaluate + Tailor (do both)")
        print("  4. Track application")
        print("  5. View application stats")
        print("  6. Exit")
        print("═" * 39)

        choice = input("Choose option: ").strip()

        if choice == "1":
            menu_evaluate(profile)
        elif choice == "2":
            menu_tailor(profile)
        elif choice == "3":
            menu_evaluate_and_tailor(profile)
        elif choice == "4":
            menu_track()
        elif choice == "5":
            show_stats()
            list_applications()
        elif choice in ("6", "q", "exit", "quit"):
            print("\nGoodbye, Chinmay! Best of luck with your job applications!\n")
            break
        else:
            print("\n[error] Invalid selection. Please enter a number from 1 to 6.\n")


if __name__ == "__main__":
    main()
