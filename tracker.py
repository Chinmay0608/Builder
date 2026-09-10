#!/usr/bin/env python3
"""
tracker.py — Root-level entry point for job-tracker.
Allows running the tracker directly from the repository root:
    python tracker.py --since 2025-01-01 --html
"""
import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
job_tracker_pkg_dir = os.path.join(root_dir, "job-tracker")
if job_tracker_pkg_dir not in sys.path:
    sys.path.insert(0, job_tracker_pkg_dir)

from job_tracker.cli import main

if __name__ == "__main__":
    main()
