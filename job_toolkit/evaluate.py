#!/usr/bin/env python3
"""
job_toolkit/evaluate.py — Evaluate whether a Job Description is worth applying to.

Runs pure local logic (no LLM API needed) using Chinmay's profile.json:
  Check 1: Hard blockers (visa, unknown tech, experience ceiling, blacklisted domains)
  Check 2: Tech stack keyword match (0-100%)
  Check 3: Experience level fit (0-1: Strong, 1-2: Good, 2-3: Borderline, 3+: Too senior)
  Check 4: Green flags count
  Check 5: Location / remote work suitability

Usage:
  python evaluate.py                (prompts to paste JD, press Enter twice to evaluate)
  python evaluate.py jd.txt         (evaluates JD from file)
  cat jd.txt | python evaluate.py   (evaluates JD from piped stdin)
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Reconfigure stdout/stderr to UTF-8 for cross-platform and Windows terminal support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(SCRIPT_DIR, "profile.json")

# Extended catalog of recognized tech keywords to scan in job descriptions
KNOWN_TECH_CATALOG = [
    # Chinmay's Core & AI Stack
    "Java", "Spring Boot", "Node.js", "Express.js", "React.js", "React",
    "MongoDB", "MySQL", "REST APIs", "REST API", "REST", "JWT", "Kafka",
    "Docker", "GitHub Actions", "JUnit", "Postman", "Git", "Claude",
    "ChatGPT", "GitHub Copilot", "Gemini", "Gemini API", "LLM",
    # Common Frontend / Backend / Fullstack
    "TypeScript", "JavaScript", "Python", "HTML", "CSS", "Next.js", "Angular",
    "Vue.js", "PostgreSQL", "Redis", "GraphQL", "Kubernetes", "AWS", "Azure",
    "GCP", "CI/CD", "Linux", "Microservices", "Tailwind CSS", "Redux",
    # Blocked / Alternative languages
    "C#", ".NET", "Elixir", "Rust", "Go", "Golang", "Kotlin", "Swift", "Ruby",
    "Ruby on Rails", "Erlang", "PHP", "C++", "C"
]


def load_profile() -> Dict[str, Any]:
    """Loads Chinmay's profile.json."""
    if not os.path.isfile(PROFILE_PATH):
        sys.exit(f"[error] profile.json not found at: {PROFILE_PATH}")
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.exit(f"[error] Failed to parse profile.json: {e}")


def read_jd_input() -> str:
    """
    Reads JD from CLI arg file, piped stdin, or interactive multi-line paste
    (press Enter twice or type END to finish).
    """
    # 1. File passed as argument
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            return f.read().strip()

    # 2. Piped stdin (e.g. cat jd.txt | python evaluate.py)
    if not sys.stdin.isatty():
        content = sys.stdin.read().strip()
        if content:
            return content

    # 3. Interactive paste
    print("=" * 60)
    print(" Paste the Job Description below.")
    print(" Press Enter TWICE (blank line) or type 'END' to evaluate:")
    print("=" * 60)
    lines: List[str] = []
    consecutive_empty = 0
    try:
        while True:
            line = input()
            if line.strip() == "END":
                break
            if line == "":
                consecutive_empty += 1
                if consecutive_empty >= 2 and len(lines) > 0:
                    break
            else:
                consecutive_empty = 0
            lines.append(line)
    except EOFError:
        pass

    text = "\n".join(lines).strip()
    return text


def extract_company_and_role(jd_text: str) -> Tuple[str, str]:
    """Attempts to infer Company and Role from JD text."""
    company = "Unknown"
    role = "Software Engineer"

    # Common role titles
    role_patterns = [
        r"(?:Job Title|Role|Position|Opening)\s*[:\-]\s*([^\n\r]+)",
        r"\b((?:Senior\s+|Junior\s+|Lead\s+|Associate\s+|Graduate\s+|Intern\s+)?(?:Full\s*Stack|Backend|Frontend|Software|Java|MERN|Web)\s+(?:Developer|Engineer|Intern(?:ship)?))\b",
        r"\b(Software Engineer\s*(?:I|II|1|2)?)\b",
        r"\b(SWE\s*Intern)\b",
    ]
    for pattern in role_patterns:
        match = re.search(pattern, jd_text, re.IGNORECASE)
        if match:
            role = match.group(1).strip()
            # Clean up trailing punctuation
            role = re.sub(r"[\.,;:].*$", "", role)
            break

    # Common company patterns
    company_patterns = [
        r"(?:Company|Organization)\s*[:\-]\s*([^\r\n,;]{2,35})",
        r"Welcome to\s+([A-Z][A-Za-z0-9&]{1,20}(?:\s+[A-Z][A-Za-z0-9&]{1,20})?)",
        r"\b(?:at|join)\s+([A-Z][A-Za-z0-9&]{1,20}(?:\s+[A-Z][A-Za-z0-9&]{1,20})?)\b",
        r"(?:About)\s*[:\-]\s*([^\r\n,;]{2,35})",
    ]
    for pattern in company_patterns:
        match = re.search(pattern, jd_text, re.IGNORECASE)
        if match:
            c = match.group(1).strip()
            # Clean up trailing words
            c = re.sub(r"[\.,;:].*$", "", c).strip()
            # Filter out false positives
            if c.lower() not in ("the", "our team", "a", "an", "this role", "we", "apply", "us"):
                company = c
                break

    return company, role


def evaluate_jd(jd_text: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Evaluates a job description against Chinmay's profile.
    Returns a dictionary of analysis results and formatted report.
    """
    if profile is None:
        profile = load_profile()

    blockers: List[str] = []
    jd_lower = jd_text.lower()

    # ----------------------------------------------------------------------
    # Check 1: Hard Blockers
    # ----------------------------------------------------------------------
    hard_blockers = profile.get("hard_blockers", {})

    # 1A. Visa & Work Authorization
    work_auth_patterns = [
        (r"\b(?:must\s+have|require[sd]?)\s+(?:the\s+)?right\s+to\s+work\s+in\s+(?:the\s+)?(?:uk|united\s+kingdom|australia|us|usa|united\s+states|eu|europe|canada)\b", "Requires local work authorization in restricted country"),
        (r"\b(?:no|not\s+offering|unable\s+to\s+offer)\s+(?:visa\s+)?sponsorship\b", "No visa sponsorship offered for overseas candidate"),
        (r"\b(?:us|uk|australian|eu)\s+citizenship\s+required\b", "Requires foreign citizenship"),
        (r"\b(?:active\s+security\s+clearance|security\s+clearance\s+required)\b", "Requires government security clearance"),
        (r"\bmust\s+be\s+authorized\s+to\s+work\s+in\s+(?:the\s+)?(?:us|usa|uk|australia|canada)\s+without\s+sponsorship\b", "Requires work authorization without sponsorship"),
    ]
    for pattern, reason in work_auth_patterns:
        if re.search(pattern, jd_text, re.IGNORECASE):
            blockers.append(reason)
            break

    # 1B. Unknown Primary Languages
    blocked_langs = hard_blockers.get("languages_not_known", [])
    found_blocked_langs = []
    for lang in blocked_langs:
        # Match word boundaries, handling special characters like C# and .NET
        if lang == "C#":
            pattern = r"(?<![a-zA-Z0-9])C#(?![a-zA-Z0-9])"
        elif lang == ".NET":
            pattern = r"(?<![a-zA-Z0-9])\.NET(?![a-zA-Z0-9])"
        elif lang in ("Go", "Rust"):
            # Ensure not matching words like "Good" or "Trust" or generic phrases
            pattern = rf"\b{lang}(?:lang)?\s+(?:developer|engineer|backend|programming|experience|code|stack)\b|\b(?:proficient|experience|expert)\s+in\s+{lang}\b"
        else:
            pattern = rf"\b{re.escape(lang)}\b"

        if re.search(pattern, jd_text, re.IGNORECASE):
            # Check if this language is a primary requirement (not just an incidental mention)
            found_blocked_langs.append(lang)

    if found_blocked_langs:
        blockers.append(f"Requires language not in Chinmay's stack: {', '.join(found_blocked_langs)}")

    # 1C. Blacklisted Domains
    domains_to_skip = hard_blockers.get("domains_to_skip", [])
    found_domains = []
    for domain in domains_to_skip:
        if re.search(rf"\b{re.escape(domain)}\b", jd_text, re.IGNORECASE):
            found_domains.append(domain)
    if found_domains:
        blockers.append(f"Role domain matches blacklist: {', '.join(found_domains)}")

    # 1D. Experience Floor & Internship Exclusion
    exp_floor = hard_blockers.get("experience_floor", 2)
    exp_match = re.search(r"(\d+)(?:\s*[-–to]\s*(\d+))?\s*\+?\s*years?(?:\s+of)?(?:\s+experience)?", jd_text, re.IGNORECASE)
    min_exp_years = 0
    if exp_match:
        try:
            min_exp_years = int(exp_match.group(1))
        except (ValueError, TypeError):
            min_exp_years = 0

    no_internships = bool(re.search(r"\b(?:excluding|not\s+including|excluding\s+any)\s+internships?\b|\bfull[- ]time\s+experience\s+only\b", jd_text, re.IGNORECASE))
    if min_exp_years > exp_floor and no_internships:
        blockers.append(f"Requires {min_exp_years}+ years excluding internships")
    elif min_exp_years >= 4:
        blockers.append(f"Senior level role ({min_exp_years}+ years experience required)")

    # ----------------------------------------------------------------------
    # Check 2: Tech Stack Keyword Match
    # ----------------------------------------------------------------------
    core_stack = set(p.lower() for p in profile.get("core_stack", []))
    ai_tools = set(p.lower() for p in profile.get("ai_tools", []))
    chinmay_skills = core_stack.union(ai_tools)

    # Normalize skill names mapping for display
    skill_display_map = {
        "java": "Java", "spring boot": "Spring Boot", "node.js": "Node.js",
        "express.js": "Express.js", "react.js": "React.js", "react": "React",
        "mongodb": "MongoDB", "mysql": "MySQL", "rest apis": "REST APIs",
        "rest api": "REST APIs", "rest": "REST APIs", "jwt": "JWT", "kafka": "Kafka",
        "docker": "Docker", "github actions": "GitHub Actions", "junit": "JUnit",
        "postman": "Postman", "git": "Git", "claude": "Claude", "chatgpt": "ChatGPT",
        "github copilot": "GitHub Copilot", "gemini": "Gemini API", "gemini api": "Gemini API",
        "llm": "LLM", "typescript": "TypeScript", "javascript": "JavaScript",
        "python": "Python", "postgresql": "PostgreSQL", "redis": "Redis",
        "graphql": "GraphQL", "kubernetes": "Kubernetes", "aws": "AWS",
        "azure": "Azure", "gcp": "GCP", "ci/cd": "CI/CD", "microservices": "Microservices",
    }

    # Find which tech catalog keywords appear in JD
    jd_tech_found = set()
    for tech in KNOWN_TECH_CATALOG:
        tech_clean = tech.lower()
        if tech == "C":
            pattern = r"(?<![a-zA-Z0-9])C(?![a-zA-Z0-9#+])"
        elif tech in ("C#", ".NET"):
            pattern = rf"(?<![a-zA-Z0-9]){re.escape(tech)}(?![a-zA-Z0-9])"
        elif tech in ("Go", "Git"):
            pattern = rf"\b{re.escape(tech)}\b"
        else:
            pattern = rf"\b{re.escape(tech_clean)}\b"

        if re.search(pattern, jd_text, re.IGNORECASE):
            # Normalize key
            norm_key = "rest apis" if tech_clean in ("rest", "rest api") else ("react" if tech_clean == "react.js" else tech_clean)
            jd_tech_found.add(norm_key)

    matched_skills = []
    missing_skills = []

    for tech_key in jd_tech_found:
        display_name = skill_display_map.get(tech_key, tech_key.title())
        # Check if matched in Chinmay's skills
        if tech_key in chinmay_skills or (tech_key == "react" and "react.js" in chinmay_skills) or (tech_key == "gemini api" and "gemini flash api" in chinmay_skills):
            matched_skills.append(display_name)
        else:
            missing_skills.append(display_name)

    total_jd_skills = len(matched_skills) + len(missing_skills)
    if total_jd_skills > 0:
        stack_match_pct = int(round((len(matched_skills) / total_jd_skills) * 100))
    else:
        stack_match_pct = 50  # Default neutral score if no specific stack mentioned

    # ----------------------------------------------------------------------
    # Check 3: Experience Fit
    # ----------------------------------------------------------------------
    is_fresher = bool(re.search(r"\b(?:fresher|freshers|new\s*grad(?:uate)?|recent\s*graduate|entry[- ]level|intern(?:ship)?|0\s*years?)\b", jd_text, re.IGNORECASE))
    
    if is_fresher or min_exp_years <= 1:
        exp_status = "✅ 0-1 years (fresher eligible)"
        exp_verdict = "strong"
    elif min_exp_years <= 2:
        exp_status = "✅ 1-2 years (internship covers this)"
        exp_verdict = "good"
    elif min_exp_years <= 3:
        exp_status = "⚠️ 2-3 years (borderline for 2027 grad)"
        exp_verdict = "borderline"
    else:
        exp_status = f"❌ {min_exp_years}+ years (likely too senior)"
        exp_verdict = "senior"

    # ----------------------------------------------------------------------
    # Check 4: Green Flags
    # ----------------------------------------------------------------------
    green_flags_list = profile.get("green_flags", [])
    matched_flags = []
    for flag in green_flags_list:
        if re.search(rf"\b{re.escape(flag)}\b", jd_text, re.IGNORECASE):
            matched_flags.append(flag)

    # ----------------------------------------------------------------------
    # Check 5: Location Suitability
    # ----------------------------------------------------------------------
    is_india = bool(re.search(r"\b(?:india|bengaluru|bangalore|hyderabad|pune|gurgaon|gurugram|noida|delhi|mumbai|jaipur|udaipur)\b", jd_text, re.IGNORECASE))
    is_remote = bool(re.search(r"\b(?:remote|work\s+from\s+home|wfh|anywhere|worldwide)\b", jd_text, re.IGNORECASE))
    is_restricted = bool(re.search(r"\b(?:uk|london|australia|sydney|melbourne|germany|berlin|netherlands|amsterdam|canada|toronto)\b", jd_text, re.IGNORECASE))

    if is_india or is_remote:
        loc_status = "✅ India / Remote"
        loc_ok = True
    elif is_restricted and not is_remote:
        loc_status = "⚠️ International Location (visa sponsorship needed)"
        loc_ok = False
    else:
        loc_status = "✅ Remote / Flexible"
        loc_ok = True

    # ----------------------------------------------------------------------
    # Recommended Resume Version
    # ----------------------------------------------------------------------
    if re.search(r"\b(?:react|node(?:\.js)?|mern|frontend|full\s*stack)\b", jd_text, re.IGNORECASE) and "React" in matched_skills:
        resume_version = "full_stack"
    elif re.search(r"\b(?:llm|generative\s*ai|gemini|prompt\s*engineering|ai\s*tools?)\b", jd_text, re.IGNORECASE):
        resume_version = "ai_llm"
    elif re.search(r"\b(?:jwt|rbac|auth|iam|oauth|security)\b", jd_text, re.IGNORECASE):
        resume_version = "security"
    elif "Java" in matched_skills or "Spring Boot" in matched_skills:
        resume_version = "java_backend"
    else:
        resume_version = "general"

    # ----------------------------------------------------------------------
    # Overall Verdict
    # ----------------------------------------------------------------------
    if blockers:
        verdict = "❌ SKIP"
        action = f"Skip — {blockers[0]}"
    elif stack_match_pct >= 55 and exp_verdict in ("strong", "good") and loc_ok:
        verdict = "✅ APPLY"
        action = f"Apply today — strong fit (use {resume_version} resume)"
    elif stack_match_pct >= 35 and exp_verdict != "senior":
        verdict = "⚠️ BORDERLINE"
        action = f"Apply with caution — align closely with {resume_version} resume"
    else:
        verdict = "❌ SKIP"
        action = "Skip — low stack match or experience mismatch"

    company, role = extract_company_and_role(jd_text)

    # Format text report
    report_lines = [
        "═" * 39,
        "JOB EVALUATION REPORT",
        "═" * 39,
        f"Company    : {company}",
        f"Role       : {role}",
        "─" * 37,
        f"VERDICT    : {verdict}",
        "─" * 37,
        f"Stack Match: {stack_match_pct}% ({len(matched_skills)}/{total_jd_skills} keywords matched)",
        f"  ✅ Matched : {', '.join(matched_skills) if matched_skills else 'None'}",
        f"  ❌ Missing : {', '.join(missing_skills) if missing_skills else 'None'}",
        "",
        f"Experience : {exp_status}",
        f"Location   : {loc_status}",
        f"Green Flags: {len(matched_flags)} found ({', '.join(matched_flags[:5]) if matched_flags else 'None'})",
        "",
        f"Blockers   : {', '.join(blockers) if blockers else 'None'}",
        "─" * 37,
        f"Resume     : Use {resume_version} version",
        f"Action     : {action}",
        "═" * 39,
    ]
    report = "\n".join(report_lines)

    return {
        "company": company,
        "role": role,
        "verdict": verdict,
        "action": action,
        "stack_match_pct": stack_match_pct,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "experience": exp_status,
        "location": loc_status,
        "green_flags_count": len(matched_flags),
        "green_flags_matched": matched_flags,
        "blockers": blockers,
        "resume_version": resume_version,
        "report": report,
    }


def main():
    profile = load_profile()
    jd_text = read_jd_input()

    if not jd_text or len(jd_text.strip()) < 20:
        sys.exit("[error] Job description text is empty or too short.")

    res = evaluate_jd(jd_text, profile)
    print("\n" + res["report"] + "\n")


if __name__ == "__main__":
    main()
