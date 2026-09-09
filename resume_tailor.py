#!/usr/bin/env python3
"""
resume_tailor.py — Core engine to tailor a LaTeX resume for a specific job posting using Groq.

Usage:
    python resume_tailor.py --resume master.tex --job job.txt --output out.tex
    python resume_tailor.py --resume master.tex --job "Raw JD text" --output out.tex
    python resume_tailor.py --resume master.tex --job-url "https://example.com/job" --output out.tex
    python resume_tailor.py --resume master.tex --job job.txt --company "Acme" --role "SWE" --compile
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Optional

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


# --------------------------------------------------------------------------
# Environment Variable / .env Loader (Standard Library only)
# --------------------------------------------------------------------------

def load_dotenv_if_present():
    """
    Lightweight .env loader using only the Python standard library.
    Checks CWD, script directory, and ~/.resume_tailor/.env.
    """
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.expanduser("~/.resume_tailor/.env"),
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass


# --------------------------------------------------------------------------
# HTML-to-Plaintext Parser (Standard Library only)
# --------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """
    Strips HTML tags and scripts/styles, returning clean plaintext
    using only Python's standard library html.parser.
    """
    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style", "noscript", "head", "title", "meta"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "noscript", "head", "title", "meta"):
            self._skip = False
        if tag.lower() in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "section", "article"):
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)

    def get_text(self) -> str:
        text = "".join(self.chunks)
        # Collapse multiple horizontal spaces/tabs into single space
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse 3+ consecutive newlines into 2
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()


def fetch_job_from_url(url: str) -> str:
    """
    Fetches web content from the given URL and strips HTML to plain text.
    Warns if content seems suspiciously short (e.g. JS-rendered SPA).

    SECURITY NOTE (SSRF):
    In this standalone CLI tool, URLs are directly provided by the local user.
    If this functionality is ever integrated into a hosted multi-tenant web service,
    an allow-list or private IP filter MUST be enforced to prevent Server-Side Request
    Forgery (e.g. blocking 127.0.0.1, 169.254.169.254, RFC1918 subnets, and non-standard ports).
    """
    clean_url = url.strip()
    if not clean_url.lower().startswith(("http://", "https://")):
        raise ValueError(f"Invalid URL '{url}'. URL must begin with http:// or https://")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(clean_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to fetch job URL '{clean_url}': {e}") from e

    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    text = parser.get_text()

    if len(text) < 200:
        print(
            "[warn] Fetched page text is very short (< 200 chars). "
            "The site may require JavaScript to render. "
            "If the result is incomplete, copy and paste the job description manually.",
            file=sys.stderr,
        )
    return text


def load_job_description(args: argparse.Namespace) -> str:
    """
    Loads the job description from --job-url, a file path passed to --job,
    or raw text passed to --job.
    """
    if args.job_url:
        return fetch_job_from_url(args.job_url)

    if args.job:
        # Check if the argument is an existing file path
        if os.path.isfile(args.job):
            try:
                with open(args.job, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as e:
                raise RuntimeError(f"Could not read job description file '{args.job}': {e}") from e
        # Otherwise treat as raw text
        return args.job

    raise ValueError("Provide --job (file path or text) or --job-url.")


# --------------------------------------------------------------------------
# Groq API Client (Urllib / Standard Library)
# --------------------------------------------------------------------------

def call_groq(system_prompt: str, user_prompt: str, model: str, api_key: str, api_base: Optional[str] = None) -> str:
    """
    Calls the Groq chat completions API (or any OpenAI-compatible endpoint) using urllib.request.
    Includes automatic retry with exponential backoff for transient network issues and rate limits (429).
    """
    endpoint = api_base or os.environ.get("GROQ_BASE_URL") or GROQ_API_URL
    if not endpoint.endswith("/chat/completions") and not endpoint.endswith("/"):
        endpoint = f"{endpoint}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }
    json_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=json_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ResumeTailor/1.0",
        },
        method="POST",
    )

    max_retries = 3
    base_delay = 2.0
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                response_body = resp.read().decode("utf-8")
                try:
                    response_json = json.loads(response_body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Failed to parse API response as JSON: {e}\nRaw output:\n{response_body[:500]}") from e

                try:
                    return response_json["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    raise RuntimeError(f"Unexpected response format from API: {response_body}") from e

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_error = f"API error (HTTP {e.code}): {err_body}"
            # Retry on rate limits (429) or transient server errors (500, 502, 503, 504)
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                sleep_time = base_delay * (2 ** (attempt - 1))
                print(f"[retry] API returned HTTP {e.code}. Retrying in {sleep_time:.1f}s (attempt {attempt}/{max_retries})...", file=sys.stderr)
                time.sleep(sleep_time)
                continue
            raise RuntimeError(last_error) from e

        except urllib.error.URLError as e:
            last_error = f"Network connection error: {e}"
            if attempt < max_retries:
                sleep_time = base_delay * (2 ** (attempt - 1))
                print(f"[retry] Network error: {e.reason}. Retrying in {sleep_time:.1f}s (attempt {attempt}/{max_retries})...", file=sys.stderr)
                time.sleep(sleep_time)
                continue
            raise RuntimeError(last_error) from e

    raise RuntimeError(f"All {max_retries} API call attempts failed. Last error: {last_error}")


# --------------------------------------------------------------------------
# LaTeX Extraction & Validation
# --------------------------------------------------------------------------

def extract_latex(model_output: str) -> str:
    """
    Strips markdown code fences (```latex ... ``` or ``` ...) if present.
    """
    fence_match = re.search(r"```(?:latex|tex)?\s*\n?(.*?)\n?```", model_output, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return model_output.strip()


def braces_balanced(tex: str) -> bool:
    """
    Checks whether curly braces { } in LaTeX are balanced,
    ignoring escaped braces (\\{ and \\}).
    """
    depth = 0
    escaped = False
    for ch in tex:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


def looks_like_latex(tex: str) -> bool:
    """
    Validates that the output contains standard LaTeX markup indicators.
    """
    has_doc_class = r"\documentclass" in tex
    has_begin_doc = r"\begin{document}" in tex
    has_section = r"\section" in tex
    return has_doc_class or has_begin_doc or has_section


# --------------------------------------------------------------------------
# System & User Prompts
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an elite executive resume writer and ATS (Applicant Tracking System) optimization specialist who edits LaTeX resumes.

STRICT RULES:
1. Output ONLY complete, compilable LaTeX source code. No explanations, no markdown fences, no conversational commentary before or after.
2. NEVER change the document structure: documentclass, packages, geometry, fonts, custom commands/macros, environments, or formatting/styling commands. Preserve them EXACTLY as given.
3. ONLY modify the actual resume CONTENT:
   - Bullet point wording and action verbs (make them impactful, metrics-driven, and aligned with the target role).
   - Summary / Objective / Profile section text.
   - Ordering and prioritization of bullets within a job/section (put the most relevant accomplishments first).
   - Ordering and grouping of skills in Skills / Technical Skills sections (put high-priority matching skills first).
4. NEVER invent employers, job titles, employment dates, degrees, certifications, or fabricated metrics/claims that are not in the original resume.
5. Weave in important keywords, tools, frameworks, and domain phrasing from the job description wherever they truthfully reflect or match the candidate's existing experience, for maximum ATS score.
6. Keep the resume to roughly the same length as the original (do not cause extra page overflow).
7. Ensure all LaTeX braces, escapes (e.g. \\%, \\&, \\$), and syntax remain 100% valid so the document compiles without errors.
8. If there is a Skills or Technical Skills section, reorder the items so the most relevant ones appear first without deleting any truthful entries.
"""


def build_user_prompt(resume_tex: str, job_description: str, company: str, role: str) -> str:
    """
    Constructs the prompt sent to Groq with context, JD, and current LaTeX resume.
    """
    target_info = []
    if company:
        target_info.append(f"Company: {company}")
    if role:
        target_info.append(f"Target Role: {role}")
    target_header = "\n".join(target_info)
    if target_header:
        target_header = f"TARGET APPLICATION:\n{target_header}\n\n"

    return f"""{target_header}TARGET JOB DESCRIPTION:
==================================================
{job_description.strip()}
==================================================

MASTER RESUME LATEX SOURCE:
==================================================
{resume_tex.strip()}
==================================================

Rewrite the master resume LaTeX above to tailor it precisely for the target job description according to all your instructions.
Return ONLY the full updated LaTeX source code, starting from \\documentclass (or the first line) to \\end{{document}}.
"""


# --------------------------------------------------------------------------
# Diff View
# --------------------------------------------------------------------------

def print_diff(original_tex: str, tailored_tex: str, original_name: str = "original.tex", tailored_name: str = "tailored.tex") -> None:
    """
    Prints a clean unified diff between the original and tailored LaTeX text.
    """
    diff = difflib.unified_diff(
        original_tex.splitlines(keepends=True),
        tailored_tex.splitlines(keepends=True),
        fromfile=original_name,
        tofile=tailored_name,
    )
    diff_lines = list(diff)
    if not diff_lines:
        print("\n[diff] No textual changes detected between original and tailored resume.\n")
        return

    print("\n" + "=" * 70)
    print("UNIFIED DIFF (Changes Made to Resume):")
    print("=" * 70)
    use_color = sys.stdout.isatty()
    for line in diff_lines:
        line_str = line.rstrip("\n")
        if line_str.startswith("+++") or line_str.startswith("---"):
            print(f"\033[1m{line_str}\033[0m" if use_color else line_str)
        elif line_str.startswith("+"):
            print(f"\033[32m{line_str}\033[0m" if use_color else line_str)
        elif line_str.startswith("-"):
            print(f"\033[31m{line_str}\033[0m" if use_color else line_str)
        elif line_str.startswith("@@"):
            print(f"\033[36m{line_str}\033[0m" if use_color else line_str)
        else:
            print(line_str)
    print("=" * 70 + "\n")


# --------------------------------------------------------------------------
# PDF Compilation
# --------------------------------------------------------------------------

def compile_pdf(tex_path: str) -> bool:
    """
    Compiles the LaTeX file to PDF. Detects available engine (latexmk, pdflatex, xelatex).
    """
    compiler = None
    for candidate in ("latexmk", "pdflatex", "xelatex"):
        if shutil.which(candidate):
            compiler = candidate
            break

    if not compiler:
        print(
            "[warn] No LaTeX compiler found on PATH (checked latexmk, pdflatex, xelatex).\n"
            "       Install TeX Live, MacTeX, or MiKTeX if you want automatic PDF builds.",
            file=sys.stderr,
        )
        return False

    abs_tex = os.path.abspath(tex_path)
    work_dir = os.path.dirname(abs_tex) or "."
    base_name = os.path.splitext(os.path.basename(abs_tex))[0]
    pdf_path = os.path.join(work_dir, f"{base_name}.pdf")

    print(f"[compile] Compiling PDF using '{compiler}'...")

    if compiler == "latexmk":
        res = subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", f"-output-directory={work_dir}", abs_tex],
            capture_output=True,
            text=True,
        )
        success = os.path.isfile(pdf_path)
        last_out = res.stdout
    else:
        # pdflatex or xelatex: run twice for cross-references
        print(f"[compile] Running {compiler} (pass 1/2)...")
        subprocess.run(
            [compiler, "-interaction=nonstopmode", "-output-directory", work_dir, abs_tex],
            capture_output=True,
            text=True,
        )
        print(f"[compile] Running {compiler} (pass 2/2)...")
        res2 = subprocess.run(
            [compiler, "-interaction=nonstopmode", "-output-directory", work_dir, abs_tex],
            capture_output=True,
            text=True,
        )
        success = os.path.isfile(pdf_path)
        last_out = res2.stdout

    if success:
        print(f"[compile] PDF successfully generated: {pdf_path}")
        return True
    else:
        print("[compile] [error] PDF compilation failed.", file=sys.stderr)
        log_snippet = (last_out or "")[-2000:]
        if log_snippet:
            print(f"----- {compiler} output (tail) -----\n{log_snippet}", file=sys.stderr)
        return False


# --------------------------------------------------------------------------
# Main CLI Entry Point
# --------------------------------------------------------------------------

def main():
    load_dotenv_if_present()

    parser = argparse.ArgumentParser(
        description="Resume Tailor — Tailor a LaTeX resume for a specific job posting using Groq AI."
    )
    parser.add_argument(
        "--resume",
        required=True,
        help="Path to your master .tex resume file",
    )
    parser.add_argument(
        "--job",
        help="Job description as raw text OR path to a .txt file containing it",
    )
    parser.add_argument(
        "--job-url",
        help="URL of the job posting to fetch and parse",
    )
    parser.add_argument(
        "--company",
        default="",
        help="Target company name (used for context and default filename)",
    )
    parser.add_argument(
        "--role",
        default="",
        help="Target role/title (used for context and default filename)",
    )
    parser.add_argument(
        "--output",
        help="Output .tex file path (default: auto-named as {resume_base}_{company}_{role}.tex)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Groq model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Compile output .tex to PDF using latexmk, pdflatex, or xelatex",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Display a unified diff between original and tailored resume",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GROQ_API_KEY"),
        help="API key (defaults to GROQ_API_KEY environment variable)",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("GROQ_BASE_URL"),
        help="API base URL (defaults to GROQ_BASE_URL or https://api.groq.com/openai/v1/chat/completions)",
    )

    args = parser.parse_args()

    # Validate API key
    api_key = args.api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("[error] No API key provided. Set GROQ_API_KEY environment variable or pass --api-key.")

    # Validate resume file
    if not os.path.isfile(args.resume):
        sys.exit(f"[error] Master resume file not found: {args.resume}")

    try:
        with open(args.resume, "r", encoding="utf-8") as f:
            resume_tex = f.read()
    except OSError as e:
        sys.exit(f"[error] Failed to read resume file: {e}")

    # [1/4] Load Job Description
    print("[1/4] Loading job description...")
    try:
        job_description = load_job_description(args)
    except Exception as e:
        sys.exit(f"[error] Failed to load job description: {e}")

    if not job_description or len(job_description.strip()) < 30:
        sys.exit("[error] Job description is empty or too short (< 30 characters).")

    # [2/4] Call Groq API
    print(f"[2/4] Sending to AI model ({args.model}) for tailoring...")
    user_prompt = build_user_prompt(resume_tex, job_description, args.company, args.role)
    try:
        raw_output = call_groq(SYSTEM_PROMPT, user_prompt, args.model, api_key, args.api_base)
    except Exception as e:
        sys.exit(f"[error] API call failed: {e}")

    # [3/4] Validate LaTeX output
    print("[3/4] Validating LaTeX output...")
    tailored_tex = extract_latex(raw_output)

    if not looks_like_latex(tailored_tex):
        sys.exit(
            "[error] Model output does not appear to be valid LaTeX. "
            "Aborting without writing any file.\n"
            "----- RAW MODEL OUTPUT (first 800 chars) -----\n"
            + raw_output[:800]
        )

    if not braces_balanced(tailored_tex):
        print(
            "[warn] Curly braces in generated LaTeX appear unbalanced. "
            "Writing file, but please review the LaTeX syntax carefully.",
            file=sys.stderr,
        )

    # Determine output file path
    if args.output:
        out_path = args.output
    else:
        base_name = os.path.splitext(os.path.basename(args.resume))[0]
        tag_parts = [p.strip() for p in (args.company, args.role) if p.strip()]
        tag = "_".join(tag_parts).replace(" ", "_") if tag_parts else "tailored"
        # Sanitize filename
        tag = re.sub(r'[\\/*?:"<>|]', "_", tag)
        out_path = f"{base_name}_{tag}.tex"

    # Ensure target directory exists
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(tailored_tex)
    except OSError as e:
        sys.exit(f"[error] Failed to write tailored resume to '{out_path}': {e}")

    # [4/4] Output saved
    print(f"[4/4] Successfully saved tailored resume to: {out_path}\n")

    # Optional diff view
    if args.diff:
        print_diff(resume_tex, tailored_tex, args.resume, out_path)

    # Always output the tailored LaTeX code to stdout for easy copy-pasting (e.g. Overleaf)
    print("=" * 70)
    print("TAILORED LATEX SOURCE CODE (Ready to copy/paste):")
    print("=" * 70)
    print(tailored_tex)
    print("=" * 70 + "\n")

    # Optional compilation
    if args.compile:
        compile_pdf(out_path)


if __name__ == "__main__":
    main()
