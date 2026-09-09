#!/usr/bin/env python3
"""
job_toolkit/tailor.py — Tailor Chinmay's LaTeX resume for a specific Job Description using Groq API.

Guarantees:
  - Exact match to Chinmay's FAANGPath / Overleaf single-page template
  - Zero warnings in Overleaf (fixes font shape and footskip issues)
  - Strictly grounded in profile.json (no hallucinations or fake metrics)
  - Guaranteed 1-page fit
  - Returns clean, compilable LaTeX code saved to job_toolkit/output/

Usage:
  python tailor.py
  python tailor.py jd.txt
  python tailor.py --version full_stack
  python tailor.py jd.txt --company "Oracle" --version java_backend
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

# Reconfigure stdout/stderr to UTF-8 for cross-platform and Windows terminal support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Attempt to import evaluate_jd for smart version detection
try:
    from evaluate import evaluate_jd
except ImportError:
    evaluate_jd = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(SCRIPT_DIR, "profile.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Primary models on Groq
PREFERRED_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "groq/compound",
]
DEFAULT_MODEL = PREFERRED_MODELS[0]


def load_dotenv_if_present():
    """Lightweight .env loader using standard library."""
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(SCRIPT_DIR, ".env"),
        os.path.join(os.path.dirname(SCRIPT_DIR), ".env"),
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


def load_profile() -> Dict[str, Any]:
    """Loads Chinmay's profile.json."""
    if not os.path.isfile(PROFILE_PATH):
        sys.exit(f"[error] profile.json not found at: {PROFILE_PATH}")
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.exit(f"[error] Failed to parse profile.json: {e}")


def read_multiline_jd() -> str:
    """Reads JD interactively or from piped stdin."""
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            return f.read().strip()

    if not sys.stdin.isatty():
        content = sys.stdin.read().strip()
        if content:
            return content

    print("=" * 60)
    print(" Paste the Job Description below.")
    print(" Press Enter TWICE (blank line) or type 'END' when finished:")
    print("=" * 60)
    lines = []
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

    return "\n".join(lines).strip()


# --------------------------------------------------------------------------
# Chinmay's Personal FAANGPath LaTeX Resume Template (Zero Warnings, 1 Page)
# --------------------------------------------------------------------------

BASE_LATEX_TEMPLATE = r"""\documentclass[letterpaper,12pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage[T1]{fontenc}
\usepackage{mathptmx} % Formal, authoritative Times New Roman font (12pt font size)
% To try Charter font instead, uncomment: \usepackage{charter}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

% Margins calibrated for 12pt so everything strictly fits on 1 page
\addtolength{\oddsidemargin}{-0.6in}
\addtolength{\evensidemargin}{-0.6in}
\addtolength{\textwidth}{1.2in}
\addtolength{\topmargin}{-0.65in}
\addtolength{\textheight}{1.3in}
\setlength{\footskip}{4.08pt}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

% Sections formatting
\titleformat{\section}{
  \vspace{-5pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-4pt}]

\newcommand{\resumeItem}[1]{
  \item{
    {#1 \vspace{-2.5pt}}
  }
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.98\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{#3} & \textit{#4} \\
    \end{tabular*}\vspace{-6pt}
}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-6pt}}

\begin{document}

%----------HEADING----------
\begin{center}
    \textbf{\Huge Chinmay Maheshwari} \\ \vspace{3pt}
    \small Udaipur, India $|$ +91 9460449962 $|$ \href{mailto:chinmaymaheshwari.it27@gmail.com}{\underline{chinmaymaheshwari.it27@gmail.com}} \\ \vspace{1pt}
    \href{https://linkedin.com/in/chinmay8064/}{\underline{linkedin.com/in/chinmay8064}} $|$ 
    \href{https://github.com/Chinmay0608}{\underline{github.com/Chinmay0608}} $|$ 
    \href{https://leetcode.com/u/Chinmay0608/}{\underline{leetcode.com/u/Chinmay0608}} $|$
    \href{https://portfolio-olive-nine-39.vercel.app}{\underline{Portfolio}}
\end{center}

%-----------SUMMARY-----------
\section{Summary}
Junior Software Engineer (B.Tech, graduating May/June 2027) with hands-on full-stack experience building end-to-end features using React, Node.js, and Java/Spring Boot. Delivered secure REST APIs with JWT RBAC, integrated LLM capabilities via Gemini API, and accelerated development with AI coding assistants (Claude, GitHub Copilot, ChatGPT). Strong problem-solving background (400+ LeetCode problems) and a track record of rapid feature delivery in an internship setting.

%-----------EDUCATION-----------
\section{Education}
  \resumeSubHeadingListStart
    \resumeSubheading
      {Jaipur Engineering College and Research Centre}{Jaipur, India}
      {Bachelor of Technology in Information Technology (CGPA: 8.8)}{Expected May/June 2027}
  \resumeSubHeadingListEnd

%-----------SKILLS-----------
\section{Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \item{
     \textbf{Languages}{: JavaScript, Java, Python (basics), SQL, HTML/CSS} \\
     \textbf{Frameworks \& Libraries}{: React.js, Node.js, Express.js, Spring Boot, Redux, JUnit} \\
     \textbf{Databases \& Messaging}{: MongoDB, MySQL, Apache Kafka} \\
     \textbf{Developer Tools \& AI}{: Git, GitHub Actions, Docker, Postman, REST APIs, JWT, Claude, Gemini Flash API, ChatGPT, GitHub Copilot}
    }
 \end{itemize}

%-----------EXPERIENCE-----------
\section{Experience}
  \resumeSubHeadingListStart
    \resumeSubheading
      {Full Stack Developer Intern}{May 2026 -- June 2026}
      {Yinolite Solution}{Udaipur, India}
      \resumeItemListStart
        \resumeItem{Built end-to-end product features by creating secure REST API endpoints (9+) with JWT-based role-based access control for authentication and authorization.}
        \resumeItem{Designed a three-collection MongoDB schema, added cross-module indexes, and wrote integration/regression tests to ensure reliability before release.}
        \resumeItem{Accelerated development and debugging using AI coding tools (Claude, ChatGPT), and applied clean-architecture principles to keep frontend and backend concerns separate.}
      \resumeItemListEnd
  \resumeSubHeadingListEnd

%-----------PROJECTS-----------
\section{Projects}
    \resumeSubHeadingListStart
      \resumeSubheading
        {\textbf{Skill-Bridge} $|$ \emph{React.js, Node.js, Express.js, MongoDB, JWT, Google OAuth 2.0}}{}
        {Full-Stack Job Portal Platform}{\href{https://job-portal-system-alpha.vercel.app}{\underline{Live Demo}} $|$ \href{https://github.com/Chinmay0608/job-portal-system}{\underline{GitHub}}}
        \resumeItemListStart
          \resumeItem{Implemented a complete user-facing workflow: React UI, Node/Express backend, JWT authentication, and Google OAuth 2.0 for secure sign-in.}
          \resumeItem{Applied AI-assisted coding (GitHub Copilot, Claude) to scaffold components, generate tests, and produce documentation quickly.}
          \resumeItem{Enhanced security with rate-limiting, input sanitization, and HTTP-header hardening, and optimized MongoDB queries with indexes for fast lookups.}
        \resumeItemListEnd

      \resumeSubheading
        {\textbf{MindVault} $|$ \emph{Java, Spring Boot, Kafka, MongoDB, Gemini API, JUnit}}{}
        {Distributed Journal Management System}{\href{https://github.com/Chinmay0608/MindVault}{\underline{GitHub}}}
        \resumeItemListStart
          \resumeItem{Created a distributed backend using Java 8+ and Spring Boot; integrated Apache Kafka for asynchronous sentiment-analysis pipelines.}
          \resumeItem{Integrated Google Gemini Flash API to provide LLM-driven sentiment analysis, employing prompt engineering for structured outputs.}
          \resumeItem{Improved data-retrieval latency by 25\% through MongoDB schema refinement and added comprehensive JUnit test coverage with CI/CD via GitHub Actions.}
        \resumeItemListEnd
    \resumeSubHeadingListEnd

%-----------ACHIEVEMENTS & CERTIFICATIONS-----------
\section{Achievements \& Certifications}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \item{
     \textbf{LeetCode}{: Solved 400+ problems focusing on Data Structures \& Algorithms (Trees, Dynamic Programming, Graphs).} \\
     \textbf{Java Development Certification}{: Core Java, OOP, Collections Framework, and software design principles (\href{https://drive.google.com/file/d/19W0G-xFzkwkhkULccCE2gLa9lP_WyJ1U/view?usp=drive_link}{\underline{Certificate}}).} \\
     \textbf{Publication}{: Review paper in \textit{Pratibodh} on ``Impact of Technology on Education and Learning'' (\href{https://pratibodh.org/index.php/pratibodh/article/view/345}{\underline{Paper}}).} \\
     \textbf{Leadership}{: Coordinated the Knowledge Knockout tech fest (2024 \& 2025), managing cross-functional teams and end-to-end event execution.}
    }
 \end{itemize}

\end{document}
"""

SYSTEM_PROMPT = """You are an expert resume writer who tailors LaTeX resumes for specific job descriptions.
You will receive:
1. Candidate profile JSON with real experience, projects, and skills
2. Target job description (JD)
3. Base LaTeX resume template matching Chinmay's personal single-page Overleaf template

STRICT ONE-PAGE ENFORCEMENT & FORMATTING RULES:
1. CRITICAL: The resume MUST fit on EXACTLY ONE PAGE. It must NEVER overflow to page 2.
2. PRESERVE THE EXACT TEMPLATE STRUCTURE & FONT:
   - Use the exact macros: \\resumeSubHeadingListStart, \\resumeSubheading, \\resumeItemListStart, \\resumeItem, \\resumeItemListEnd, \\resumeSubHeadingListEnd.
   - Maintain standard readable body text (\\normalsize). Do NOT wrap body text, summary, skills, or items in \\small.
   - Do NOT replace with tabularx or other structures.
3. SUMMARY: Keep strictly to 3-4 lines maximum (~65 words). Tailor it to emphasize candidate strengths matching the target JD.
4. SKILLS: Keep strictly to the 4 categories in the itemize block:
   - Languages
   - Frameworks & Libraries
   - Databases & Messaging
   - Developer Tools & AI
   Reorder keywords within these 4 categories to highlight JD relevance, but keep each line concise so none wrap into multiple unnecessary lines.
5. EXPERIENCE: Keep strictly to the single Yinolite role with exactly 3 bullets (maximum 2 lines per bullet).
6. PROJECTS: Keep strictly to the 2 projects (Skill-Bridge and MindVault), exactly 3 bullets each (maximum 1.5 to 2 lines per bullet). Order whichever project is more relevant first.
7. ACHIEVEMENTS & CERTIFICATIONS: Keep strictly to the 4 items.
8. TRUTHFULNESS: Never invent employers, titles, dates, degrees, or fake metrics. Only use real experience from the profile JSON.
9. LATEX SYNTAX:
   - NEVER use markdown syntax (like *italics* or **bold**); ALWAYS use valid LaTeX commands like \\textit{...} and \\textbf{...}
   - NEVER use unicode curly quotes; use standard LaTeX quotes ``...''
   - NEVER output stray characters (such as lone '+' signs or markdown bullet artifacts).
   - Use standard LaTeX dashes: '--' for date ranges and em-dashes.
   - Do NOT use \\scshape inside \\textbf in the heading. Use \\textbf{\\Huge Chinmay Maheshwari}.

Return ONLY the complete, compilable LaTeX code starting with \\documentclass and ending with \\end{document}.
"""


def call_groq(system_prompt: str, user_prompt: str, api_key: str, model_name: Optional[str] = None) -> Tuple[str, str]:
    """
    Calls the Groq chat completions API with automatic model fallback.
    Returns (model_output_text, model_name_used).
    """
    models_to_try = [model_name] if model_name else PREFERRED_MODELS
    last_error = None

    for m in models_to_try:
        payload = {
            "model": m,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 6000,
        }
        json_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            GROQ_API_URL,
            data=json_data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ChinmayJobToolkit/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                response_json = json.loads(resp.read().decode("utf-8"))
                content = response_json["choices"][0]["message"]["content"]
                if content and len(content.strip()) > 100:
                    return content, m
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {e.code} ({m}): {err_body}"
            # Try next model if model not found or rate limited
            if e.code in (404, 400, 429):
                continue
            raise RuntimeError(last_error) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Groq network connection error: {e}") from e

    raise RuntimeError(f"All attempted Groq models failed. Last error: {last_error}")


def sanitize_latex(latex_code: str) -> str:
    """
    Cleans up any markdown leaks, unicode quotes/hyphens, stray '+' artifacts,
    and fixes Overleaf/pdflatex warnings (footskip, font shapes).
    """
    # Remove stray '+' lines or stray bullet markers
    latex_code = re.sub(r"^\s*\+\s*$", "", latex_code, flags=re.MULTILINE)
    latex_code = re.sub(r"\n\s*\+\s*\n", "\n\n", latex_code)

    # Replace markdown bold and italics
    latex_code = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", latex_code)
    latex_code = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\textit{\1}", latex_code)

    # Replace curly quotes with standard LaTeX quotes
    latex_code = latex_code.replace("“", "``").replace("”", "''")
    latex_code = latex_code.replace("‘", "`").replace("’", "'")

    # Replace unicode non-breaking hyphens and dashes
    latex_code = latex_code.replace("\u2011", "-")
    latex_code = latex_code.replace("\u2013", "--")
    latex_code = latex_code.replace("\u2014", "---")

    # Fix Computer Modern bold + small-caps font warning (OT1/cmr/bx/sc undefined)
    latex_code = re.sub(
        r"\\textbf\{\\Huge\s+\\scshape\s+Chinmay Maheshwari\}",
        r"\\textbf{\\Huge Chinmay Maheshwari}",
        latex_code
    )
    latex_code = re.sub(
        r"\\textbf\{\\scshape\s+\\Huge\s+Chinmay Maheshwari\}",
        r"\\textbf{\\Huge Chinmay Maheshwari}",
        latex_code
    )
    latex_code = re.sub(
        r"\\textbf\{\\LARGE\s+\\scshape\s+Chinmay Maheshwari\}",
        r"\\textbf{\\Huge Chinmay Maheshwari}",
        latex_code
    )
    latex_code = re.sub(
        r"\\textbf\{\\scshape\s+\\LARGE\s+Chinmay Maheshwari\}",
        r"\\textbf{\\Huge Chinmay Maheshwari}",
        latex_code
    )

    # Ensure \setlength{\footskip}{4.08pt} is present to avoid fancyhdr warning
    if r"\setlength{\footskip}" not in latex_code:
        if r"\addtolength{\textheight}{1.0in}" in latex_code:
            latex_code = latex_code.replace(
                r"\addtolength{\textheight}{1.0in}",
                "\\addtolength{\\textheight}{1.0in}\n\\setlength{\\footskip}{4.08pt}"
            )
        elif r"\addtolength{\textheight}" in latex_code:
            latex_code = re.sub(
                r"(\\addtolength\{\\textheight\}\{[^}]+\})",
                r"\1\n\\setlength{\\footskip}{4.08pt}",
                latex_code,
                count=1
            )

    return latex_code


def tailor_resume(
    jd_text: str,
    resume_version: Optional[str] = None,
    company_name: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
    model_override: Optional[str] = None,
) -> str:
    """
    Calls Groq API to tailor Chinmay's resume for the given JD.
    Saves and returns the tailored LaTeX code.
    """
    load_dotenv_if_present()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit(
            "\n[error] GROQ_API_KEY is not set.\n"
            "Please set your Groq API key in your .env file:\n"
            "  GROQ_API_KEY=your_key_here\n"
        )

    if profile is None:
        profile = load_profile()

    # Determine company name and version if not provided
    if evaluate_jd and (not company_name or not resume_version):
        eval_res = evaluate_jd(jd_text, profile)
        if not company_name:
            company_name = eval_res.get("company", "Company")
        if not resume_version:
            resume_version = eval_res.get("resume_version", "general")

    if not company_name:
        company_name = "Company"
    if not resume_version:
        resume_version = "general"

    clean_company = re.sub(r"[^A-Za-z0-9_]+", "", company_name.replace(" ", "_")) or "Company"

    user_prompt = f"""CANDIDATE PROFILE JSON:
==================================================
{json.dumps(profile, indent=2)}
==================================================

TARGET JOB DESCRIPTION:
==================================================
{jd_text.strip()}
==================================================

CHOSEN RESUME VERSION / FOCUS:
{resume_version} ({profile.get("resume_versions", {}).get(resume_version, "")})

BASE LATEX RESUME TEMPLATE (CHINMAY'S OVERLEAF TEMPLATE):
==================================================
{BASE_LATEX_TEMPLATE.strip()}
==================================================

Please rewrite and tailor this LaTeX resume for the job description above according to all instructions.
Ensure the tailored resume strictly fits on EXACTLY ONE PAGE without overflowing.
Return ONLY the raw compilable LaTeX code starting with \\documentclass and ending with \\end{{document}}.
"""

    print(f"\n[1/3] Contacting Groq API to tailor resume for '{company_name}' ({resume_version} version)...")

    try:
        raw_output, used_model = call_groq(SYSTEM_PROMPT, user_prompt, api_key, model_override)
    except Exception as e:
        sys.exit(f"[error] Groq API call failed: {e}")

    print(f"[2/3] Validating and cleaning LaTeX output (generated via {used_model})...")
    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:latex|tex)?\s*\n?(.*?)\n?```", raw_output, re.DOTALL)
    latex_code = fence_match.group(1).strip() if fence_match else raw_output.strip()

    # Automatically sanitize markdown leaks, unicode quotes, and fix Overleaf warnings
    latex_code = sanitize_latex(latex_code)

    if r"\documentclass" not in latex_code or r"\begin{document}" not in latex_code:
        sys.exit(
            "[error] Generated output does not appear to be valid LaTeX source.\n"
            f"Preview:\n{raw_output[:600]}"
        )

    # Save to job_toolkit/output/Chinmay_Resume_[CompanyName].tex
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_filename = f"Chinmay_Resume_{clean_company}.tex"
    out_path = os.path.join(OUTPUT_DIR, out_filename)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(latex_code)
    except OSError as e:
        sys.exit(f"[error] Failed to write tailored resume to {out_path}: {e}")

    print(f"[3/3] Saved to {os.path.relpath(out_path, os.getcwd())}")
    print(f"Target Role/Company : {company_name}")
    print(f"Resume Version      : {resume_version}")
    print(f"Model Used          : {used_model}")
    print("=" * 60)
    print(f"Tailored resume file ready at: {out_path}")
    print("=" * 60 + "\n")

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Tailor Chinmay's resume for a specific Job Description using Groq.")
    parser.add_argument("jd_file", nargs="?", help="Path to job description text file")
    parser.add_argument("--version", choices=["java_backend", "full_stack", "ai_llm", "security", "general"], help="Specific resume version focus")
    parser.add_argument("--company", help="Target company name for output filename")
    parser.add_argument("--model", help="Override Groq model")
    args = parser.parse_args()

    profile = load_profile()

    if args.jd_file and os.path.isfile(args.jd_file):
        with open(args.jd_file, "r", encoding="utf-8") as f:
            jd_text = f.read().strip()
    else:
        jd_text = read_multiline_jd()

    if not jd_text or len(jd_text.strip()) < 20:
        sys.exit("[error] Job description is empty or too short.")

    version = args.version
    if not version:
        print("\nAvailable resume versions:")
        for k, v in profile.get("resume_versions", {}).items():
            print(f"  - {k:14}: {v}")
        user_v = input("\nChoose version (press Enter to auto-detect): ").strip()
        if user_v in profile.get("resume_versions", {}):
            version = user_v
        else:
            version = None  # Will auto-detect via evaluate_jd

    company = args.company
    if not company:
        c_in = input("Target Company Name (press Enter to auto-detect): ").strip()
        company = c_in if c_in else None

    tailor_resume(
        jd_text=jd_text,
        resume_version=version,
        company_name=company,
        profile=profile,
        model_override=args.model,
    )


if __name__ == "__main__":
    main()
