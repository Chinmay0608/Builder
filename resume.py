#!/usr/bin/env python3
"""
resume_tailor.py — Tailor a LaTeX resume to a specific job in one command.

Usage examples:
    python resume_tailor.py --resume master.tex --job job.txt --output out.tex
    python resume_tailor.py --resume master.tex --job "paste JD text here" --output out.tex
    python resume_tailor.py --resume master.tex --job-url "https://example.com/job/123" --output out.tex
    python resume_tailor.py --resume master.tex --job job.txt --company "Acme" --role "Backend Engineer" --compile

Requires:
    pip install requests --break-system-packages
    export GROQ_API_KEY="your_key_here"
"""

import argparse
import os
import re
import sys
import subprocess
import urllib.request
from html.parser import HTMLParser

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


# --------------------------------------------------------------------------
# Helpers: fetching + cleaning job descriptions
# --------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Minimal HTML-to-text extractor (no external deps)."""
    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3"):
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)

    def get_text(self):
        text = "".join(self.chunks)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()


def fetch_job_from_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    parser = _TextExtractor()
    parser.feed(raw)
    text = parser.get_text()
    if len(text) < 200:
        print("[warn] Fetched page text looks short — the site may need JS to render. "
              "Consider pasting the JD manually instead.", file=sys.stderr)
    return text


def load_job_description(args) -> str:
    if args.job_url:
        return fetch_job_from_url(args.job_url)
    if args.job:
        if os.path.isfile(args.job):
            with open(args.job, "r", encoding="utf-8") as f:
                return f.read()
        return args.job  # treat as raw pasted text
    raise ValueError("Provide --job (text or file path) or --job-url")


# --------------------------------------------------------------------------
# Groq call
# --------------------------------------------------------------------------

def call_groq(system_prompt: str, user_prompt: str, model: str, api_key: str) -> str:
    import json
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq API error {e.code}: {body}") from e
    return data["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------
# LaTeX extraction / validation
# --------------------------------------------------------------------------

def extract_latex(model_output: str) -> str:
    """Model sometimes wraps output in ```latex fences — strip them."""
    fence_match = re.search(r"```(?:latex|tex)?\s*(.*?)```", model_output, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return model_output.strip()


def braces_balanced(tex: str) -> bool:
    depth = 0
    for ch in tex:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


def looks_like_latex(tex: str) -> bool:
    return bool(re.search(r"\\documentclass|\\begin\{document\}", tex)) or "\\section" in tex


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert resume writer and ATS optimization specialist who edits LaTeX resumes.

STRICT RULES:
1. Output ONLY the complete, compilable LaTeX source code. No explanations, no markdown fences, no commentary before or after.
2. NEVER change the LaTeX document structure, packages, class, custom commands, geometry, fonts, or formatting/styling commands. Preserve them EXACTLY as given.
3. ONLY modify the actual resume CONTENT: bullet point wording, the professional summary/objective, the ordering of skills, and the ordering/emphasis of bullets within a section (most relevant to the job first).
4. Do not invent employers, dates, degrees, or job titles that are not in the original resume. Do not fabricate metrics or claims. You may rephrase and re-emphasize truthful content and incorporate the job's terminology/keywords where they truthfully apply to the candidate's real experience.
5. Mirror important keywords, tools, and phrasing from the job description into the resume content (for ATS matching) wherever they are truthfully supported by the candidate's existing experience.
6. Keep the resume to the same approximate length as the original (do not let it grow substantially longer).
7. Preserve every LaTeX command, brace, and escape character correctly — the output must compile without errors.
8. If the resume has a "Skills" or "Technical Skills" section, reorder/reprioritize entries so the most job-relevant ones appear first, without removing truthful entries.
"""


def build_user_prompt(resume_tex: str, job_description: str, company: str, role: str) -> str:
    header = ""
    if company or role:
        header = f"Target role: {role or 'N/A'} at {company or 'N/A'}.\n\n"
    return f"""{header}JOB DESCRIPTION:
---
{job_description.strip()}
---

CURRENT LATEX RESUME (master version):
---
{resume_tex}
---

Rewrite the LaTeX resume above to be tailored for this specific job, following all the rules in your instructions.
Return ONLY the full updated LaTeX source, starting from \\documentclass (or the first line of the given source) to the final \\end{{document}}.
"""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Tailor a LaTeX resume to a job in one command.")
    parser.add_argument("--resume", required=True, help="Path to your master .tex resume file")
    parser.add_argument("--job", help="Job description text OR path to a .txt file containing it")
    parser.add_argument("--job-url", help="URL of the job posting to fetch")
    parser.add_argument("--company", default="", help="Company name (optional, improves tailoring)")
    parser.add_argument("--role", default="", help="Role/title (optional, improves tailoring)")
    parser.add_argument("--output", help="Output .tex file path (default: auto-named)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Groq model (default: {DEFAULT_MODEL})")
    parser.add_argument("--compile", action="store_true", help="Also compile output to PDF via pdflatex")
    parser.add_argument("--api-key", default=os.environ.get("GROQ_API_KEY"),
                         help="Groq API key (or set GROQ_API_KEY env var)")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("[error] No Groq API key. Set GROQ_API_KEY env var or pass --api-key.")

    if not os.path.isfile(args.resume):
        sys.exit(f"[error] Resume file not found: {args.resume}")

    with open(args.resume, "r", encoding="utf-8") as f:
        resume_tex = f.read()

    print("[1/4] Loading job description...")
    try:
        job_description = load_job_description(args)
    except Exception as e:
        sys.exit(f"[error] Failed to load job description: {e}")

    if len(job_description.strip()) < 30:
        sys.exit("[error] Job description looks empty or too short.")

    print(f"[2/4] Sending to Groq ({args.model}) for tailoring...")
    user_prompt = build_user_prompt(resume_tex, job_description, args.company, args.role)
    try:
        model_output = call_groq(SYSTEM_PROMPT, user_prompt, args.model, args.api_key)
    except Exception as e:
        sys.exit(f"[error] Groq API call failed: {e}")

    print("[3/4] Validating LaTeX output...")
    tailored_tex = extract_latex(model_output)

    if not looks_like_latex(tailored_tex):
        sys.exit("[error] Model output doesn't look like LaTeX. Aborting without overwriting anything.\n"
                  "----- RAW OUTPUT (first 800 chars) -----\n" + model_output[:800])

    if not braces_balanced(tailored_tex):
        print("[warn] Brace count looks unbalanced — please review the output carefully before compiling.",
              file=sys.stderr)

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.resume))[0]
        tag = "_".join(filter(None, [args.company, args.role])).replace(" ", "_") or "tailored"
        out_path = f"{base}_{tag}.tex"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(tailored_tex)
    print(f"[4/4] Saved tailored resume to: {out_path}")

    if args.compile:
        compile_pdf(out_path)


def compile_pdf(tex_path: str):
    if not shutil_which("pdflatex"):
        print("[warn] pdflatex not found on PATH — skipping PDF compile. "
              "Install a LaTeX distribution (e.g. TeX Live) to enable this.", file=sys.stderr)
        return
    out_dir = os.path.dirname(os.path.abspath(tex_path)) or "."
    print("[compile] Running pdflatex (twice, for refs/formatting)...")
    for _ in range(2):
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-output-directory", out_dir, tex_path],
            capture_output=True, text=True
        )
    pdf_path = os.path.splitext(tex_path)[0] + ".pdf"
    if os.path.isfile(pdf_path):
        print(f"[compile] PDF generated: {pdf_path}")
    else:
        print("[compile] PDF compilation failed. Last pdflatex output:\n" + result.stdout[-2000:],
              file=sys.stderr)


def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)


if __name__ == "__main__":
    main()