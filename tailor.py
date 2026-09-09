#!/usr/bin/env python3
"""
tailor.py — One-command wrapper for Resume Tailor with persistent config & flexible JD input.

Supports multiple JD input modes:
  1. URL:          python tailor.py "https://jobs.example.com/123"
  2. File:         python tailor.py jd.txt
  3. Interactive:  python tailor.py --paste (or simply 'python tailor.py')
  4. Piped stdin:  cat jd.txt | python tailor.py
                   pbpaste | python tailor.py
                   Get-Content jd.txt | python tailor.py
"""

import argparse
import json
import os
import re
import subprocess
import sys

CONFIG_DIR = os.path.expanduser("~/.resume_tailor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
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
# Configuration Management
# --------------------------------------------------------------------------

def load_config() -> dict:
    """
    Loads saved configuration from ~/.resume_tailor/config.json if it exists.
    Returns None if the file is missing or invalid.
    """
    if not os.path.isfile(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[warn] Failed to read config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return None


def run_setup(existing_config: dict = None) -> dict:
    """
    Runs an interactive configuration wizard to prompt for and save
    user settings (master resume path, Groq API key, model, output dir, auto_compile).
    """
    print("\n" + "=" * 60)
    print("         Resume Tailor — Configuration Setup")
    print("=" * 60)
    print("Press Enter to accept [default values] shown in brackets.\n")

    cfg = existing_config or {}

    # 1. Master resume path
    current_resume = cfg.get("resume_path", "")
    while True:
        prompt_str = f"Master .tex resume path [{current_resume}]: " if current_resume else "Master .tex resume path: "
        val = input(prompt_str).strip()
        resume_path = val or current_resume
        resume_path = os.path.expanduser(resume_path)
        if not resume_path:
            print("[error] Master resume path is required.")
            continue
        if not os.path.isfile(resume_path):
            print(f"[error] File not found at '{resume_path}'. Please enter a valid path.")
            continue
        break

    # 2. Groq API Key
    default_key = cfg.get("api_key") or os.environ.get("GROQ_API_KEY", "")
    if len(default_key) > 10:
        masked_key = f"{default_key[:6]}...{default_key[-4:]}"
        prompt_str = f"Groq API Key [{masked_key}]: "
    elif default_key:
        prompt_str = f"Groq API Key [{default_key}]: "
    else:
        prompt_str = "Groq API Key: "

    val = input(prompt_str).strip()
    api_key = val or default_key
    if not api_key:
        print("[warn] No API key entered. You will need to set the GROQ_API_KEY environment variable.")

    # 3. Model
    current_model = cfg.get("model", DEFAULT_MODEL)
    val = input(f"Groq Model [{current_model}]: ").strip()
    model = val or current_model

    # 4. Output Directory
    current_outdir = cfg.get("output_dir", "./tailored_resumes")
    val = input(f"Output directory for tailored resumes [{current_outdir}]: ").strip()
    output_dir = os.path.expanduser(val or current_outdir)

    # 5. Auto compile to PDF
    current_compile = cfg.get("auto_compile", False)
    compile_default_str = "Y/n" if current_compile else "y/N"
    val = input(f"Automatically compile to PDF with pdflatex? [{compile_default_str}]: ").strip().lower()
    if val in ("y", "yes"):
        auto_compile = True
    elif val in ("n", "no"):
        auto_compile = False
    else:
        auto_compile = current_compile

    config = {
        "resume_path": os.path.abspath(resume_path),
        "api_key": api_key,
        "model": model,
        "output_dir": os.path.abspath(output_dir),
        "auto_compile": auto_compile,
    }

    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"\n[setup] Configuration successfully saved to:\n        {CONFIG_FILE}\n")
    except OSError as e:
        sys.exit(f"[error] Failed to save configuration to '{CONFIG_FILE}': {e}")

    return config


# --------------------------------------------------------------------------
# Multi-line Interactive Input Helper
# --------------------------------------------------------------------------

def read_multiline_paste() -> str:
    """
    Prompts the user to paste a multi-line job description interactively.
    Ends on a lone line containing 'END' or EOF (Ctrl+D / Ctrl+Z).
    """
    print("=" * 60)
    print(" Paste the Job Description below.")
    print(" Type 'END' on a new line or press Ctrl+D / Ctrl+Z + Enter to finish:")
    print("=" * 60)
    lines = []
    try:
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
    except EOFError:
        pass

    text = "\n".join(lines).strip()
    if not text:
        sys.exit("[error] No job description provided. Aborting.")
    return text


# --------------------------------------------------------------------------
# Main Dispatch
# --------------------------------------------------------------------------

def main():
    load_dotenv_if_present()

    parser = argparse.ArgumentParser(
        description="Resume Tailor — Tailor your LaTeX resume for any job with a single command.",
        usage="python tailor.py [job_arg] [-c COMPANY] [-r ROLE] [--paste] [--new-resume PATH] [--compile] [--setup]",
    )
    parser.add_argument(
        "job_arg",
        nargs="?",
        help="Job description as a URL, file path (.txt), or inline text",
    )
    parser.add_argument(
        "-c", "--company",
        default=None,
        help="Target company name (skips interactive prompt if provided)",
    )
    parser.add_argument(
        "-r", "--role",
        default=None,
        help="Target role/title (skips interactive prompt if provided)",
    )
    parser.add_argument(
        "--paste",
        action="store_true",
        help="Prompt for interactive multi-line paste of the job description",
    )
    parser.add_argument(
        "--new-resume",
        help="Override master resume path for this run",
    )
    parser.add_argument(
        "--model",
        help=f"Override configured Groq model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--setup", "--config",
        action="store_true",
        dest="setup",
        help="Run interactive setup wizard to configure settings",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Force compilation of the tailored LaTeX file to PDF",
    )

    args = parser.parse_args()

    # Load existing config
    config = load_config()

    # If --setup or --config flag passed, run wizard and exit
    if args.setup:
        run_setup(config)
        return

    # If no config exists, run wizard automatically on first run
    if not config:
        print("[info] No config found at ~/.resume_tailor/config.json.")
        print("[info] Starting first-time setup wizard...\n")
        config = run_setup()

    # 1. Determine master resume path
    resume_path = args.new_resume or config.get("resume_path")
    if not resume_path:
        sys.exit("[error] No master resume path configured. Run 'python tailor.py --setup' or pass --new-resume.")
    resume_path = os.path.expanduser(resume_path)
    if not os.path.isfile(resume_path):
        sys.exit(
            f"[error] Master resume file not found: '{resume_path}'.\n"
            f"        Run 'python tailor.py --setup' to update your configuration."
        )

    # 2. Determine Job Description source according to strict priority:
    #    Priority: --paste > positional arg > piped stdin > interactive fallback
    is_interactive_terminal = sys.stdin.isatty()
    job_source = None
    is_url = False

    if args.paste:
        job_source = read_multiline_paste()
    elif args.job_arg:
        arg_val = args.job_arg.strip()
        if re.match(r"^https?://", arg_val):
            job_source = arg_val
            is_url = True
        elif os.path.isfile(arg_val):
            job_source = os.path.abspath(arg_val)
        else:
            # Inline raw text
            job_source = arg_val
    elif not is_interactive_terminal:
        # Piped stdin (e.g. cat jd.txt | python tailor.py)
        job_source = sys.stdin.read().strip()
        if not job_source:
            sys.exit("[error] Piped stdin was empty. Aborting.")
    else:
        # Fallback to interactive multi-line paste
        job_source = read_multiline_paste()

    # 3. Determine Company and Role:
    #    Only prompt interactively if stdin is an interactive terminal and args were not provided
    company = args.company
    role = args.role

    if is_interactive_terminal and not args.paste and args.job_arg:
        # If passed via positional arg, prompt for company/role only if omitted
        if company is None:
            company = input("Target Company (optional, press Enter to skip): ").strip()
        if role is None:
            role = input("Target Role / Job Title (optional, press Enter to skip): ").strip()
    else:
        # If piped stdin or --paste mode without CLI flags, default to empty string if None
        company = company or ""
        role = role or ""

    # 4. Auto-compute output path in output_dir
    output_dir = os.path.expanduser(config.get("output_dir", "."))
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(resume_path))[0]
    tag_parts = [p.strip() for p in (company, role) if p and p.strip()]
    tag = "_".join(tag_parts).replace(" ", "_") if tag_parts else "tailored"
    tag = re.sub(r'[\\/*?:"<>|]', "_", tag)
    output_filename = f"{base_name}_{tag}.tex"
    output_path = os.path.join(output_dir, output_filename)

    # 5. Locate core engine (resume_tailor.py)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    engine_path = os.path.join(script_dir, "resume_tailor.py")
    if not os.path.isfile(engine_path):
        engine_path = "resume_tailor.py"

    # 6. Build command line arguments for resume_tailor.py
    model_name = args.model or config.get("model", DEFAULT_MODEL)
    cmd = [
        sys.executable,
        engine_path,
        "--resume", resume_path,
        "--output", output_path,
        "--model", model_name,
    ]

    if is_url:
        cmd.extend(["--job-url", job_source])
    else:
        cmd.extend(["--job", job_source])

    if company:
        cmd.extend(["--company", company])
    if role:
        cmd.extend(["--role", role])

    api_key = config.get("api_key") or os.environ.get("GROQ_API_KEY")
    if api_key:
        cmd.extend(["--api-key", api_key])

    # Pass compile flag if requested via CLI or config
    if args.compile or config.get("auto_compile", False):
        cmd.append("--compile")

    # 7. Execute resume_tailor.py replacing current process
    try:
        os.execvp(sys.executable, cmd)
    except Exception:
        # Fallback in environments where execvp might not replace process
        res = subprocess.run(cmd)
        sys.exit(res.returncode)


if __name__ == "__main__":
    main()
