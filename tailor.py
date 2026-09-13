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

# Reconfigure stdout/stderr to UTF-8 for cross-platform and Windows terminal support
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

CONFIG_DIR = os.path.expanduser("~/.resume_tailor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_MODEL = "qwen/qwen3.8-27b"


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
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
        # Write config with restrictive 0600 permissions to protect API key
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        try:
            fd = os.open(CONFIG_FILE, flags, mode)
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            try:
                os.chmod(CONFIG_FILE, 0o600)
            except Exception:
                pass
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
        usage="python tailor.py [job_arg] [-c COMPANY] [-r ROLE] [--paste] [--new-resume PATH] [--compile] [--setup] [--evaluate-only]",
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
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Display unified diff between original and tailored resume",
    )
    parser.add_argument(
        "--api-base",
        help="Custom OpenAI-compatible API base URL (e.g. for Ollama or other endpoints)",
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Evaluate the job description without tailoring a resume",
    )

    args = parser.parse_args()

    # Load existing config
    config = load_config()

    # If --setup or --config flag passed, run wizard and exit
    if args.setup:
        run_setup(config)
        return

    # If no config exists, auto-detect master_resume.tex or run wizard
    if not config and not args.evaluate_only:
        has_any_key = any(
            (k == "GROQ_API_KEY" or k.startswith("GROQ_API_KEY_") or k == "GROQ_API_KEYS") and v.strip()
            for k, v in os.environ.items()
        )
        if os.path.isfile("master_resume.tex") and has_any_key:
            config = {
                "resume_path": os.path.abspath("master_resume.tex"),
                "model": DEFAULT_MODEL,
                "output_dir": "./tailored_resumes",
                "auto_compile": False,
            }
        else:
            print("[info] No config found at ~/.resume_tailor/config.json.")
            print("[info] Starting first-time setup wizard...\n")
            config = run_setup()

    # 1. Determine Job Description source according to strict priority:
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

    # Resolve job description text for evaluation
    if is_url:
        from resume_tailor import fetch_job_from_url
        try:
            jd_text = fetch_job_from_url(job_source)
        except Exception as e:
            sys.exit(f"[error] Failed to fetch job URL: {e}")
    elif os.path.isfile(job_source):
        try:
            with open(job_source, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except OSError as e:
            sys.exit(f"[error] Failed to read job description file '{job_source}': {e}")
    else:
        jd_text = job_source

    # ----------------------------------------------------------------------
    # STEP 1/2: JD Evaluation
    # ----------------------------------------------------------------------
    from evaluate import local_evaluate, ai_evaluate, display_evaluation

    print("\n[STEP 1/2] Evaluating JD...")
    local_result = local_evaluate(jd_text)

    api_key = (config.get("api_key") if config else None) or os.environ.get("GROQ_API_KEY")
    model_name = args.model or (config.get("model") if config else DEFAULT_MODEL) or DEFAULT_MODEL
    api_base = args.api_base or (config.get("api_base") if config else None) or os.environ.get("GROQ_BASE_URL")

    # If --evaluate-only requested, run evaluation and exit cleanly
    if args.evaluate_only:
        ai_result = None
        if api_key or os.environ.get("GROQ_API_KEY_2") or os.environ.get("GROQ_API_KEYS"):
            ai_result = ai_evaluate(jd_text, api_key=api_key, model=model_name, api_base=api_base)
        display_evaluation(local_result, ai_result)
        sys.exit(0)

    # If hard blocks found in local check — display and ask before proceeding
    if local_result["local_verdict"] == "SKIP":
        display_evaluation(local_result)
        try:
            confirm = input("Hard blocks found. Tailor resume anyway? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nSkipped. No resume generated.")
            sys.exit(0)
        if confirm != "y":
            print("Skipped. No resume generated.")
            sys.exit(0)

    # Run AI evaluation if API key available
    ai_result = None
    if api_key or os.environ.get("GROQ_API_KEY_2") or os.environ.get("GROQ_API_KEYS"):
        ai_result = ai_evaluate(jd_text, api_key=api_key, model=model_name, api_base=api_base)

    display_evaluation(local_result, ai_result)

    # If SKIP verdict from AI — confirm before proceeding
    if (ai_result and ai_result.get("verdict") == "SKIP") or local_result["local_verdict"] == "SKIP":
        try:
            confirm = input("Verdict is SKIP. Tailor resume anyway? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nSkipped. No resume generated.")
            sys.exit(0)
        if confirm != "y":
            print("Skipped. No resume generated.")
            sys.exit(0)

    print("\n[STEP 2/2] Tailoring resume...")

    # 2. Determine master resume path
    resume_path = args.new_resume or (config.get("resume_path") if config else None)
    if not resume_path:
        sys.exit("[error] No master resume path configured. Run 'python tailor.py --setup' or pass --new-resume.")
    resume_path = os.path.expanduser(resume_path)
    if not os.path.isfile(resume_path):
        sys.exit(
            f"[error] Master resume file not found: '{resume_path}'.\n"
            f"        Run 'python tailor.py --setup' to update your configuration."
        )

    # 3. Determine Company and Role:
    company = args.company
    role = args.role

    # Auto-populate company / role from AI analysis if not explicitly provided
    if ai_result:
        extracted_comp = ai_result.get("company", "").strip()
        if not company and extracted_comp and extracted_comp.lower() != "unknown":
            company = extracted_comp
        extracted_role = ai_result.get("role", "").strip()
        if not role and extracted_role and extracted_role.lower() != "unknown":
            role = extracted_role

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

    api_key = config.get("api_key")
    if api_key:
        cmd.extend(["--api-key", api_key])

    if args.compile or config.get("auto_compile", False):
        cmd.append("--compile")

    if args.diff:
        cmd.append("--diff")

    api_base = args.api_base or config.get("api_base") or os.environ.get("GROQ_BASE_URL")
    if api_base:
        cmd.extend(["--api-base", api_base])

    # 7. Execute resume_tailor.py replacing current process
    try:
        os.execvp(sys.executable, cmd)
    except Exception:
        # Fallback in environments where execvp might not replace process
        res = subprocess.run(cmd)
        sys.exit(res.returncode)


if __name__ == "__main__":
    main()
