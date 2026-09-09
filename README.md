# Resume Tailor (Builder)

A fast, lightweight, zero-dependency command-line tool that tailors a LaTeX (`.tex`) resume for a specific job posting in **one single command** using the ultra-fast Groq API (`llama-3.3-70b-versatile`) or any OpenAI-compatible LLM endpoint.

It outputs the tailored LaTeX code directly to the console for quick copy-pasting (e.g. into Overleaf), prints an instant terminal unified diff (`--diff`), and saves the tailored `.tex` file to disk (with optional multi-engine PDF compilation).

---

## ✨ Key Features

- **One-Command Workflow**: Once configured, tailor any resume in seconds: `tailor jd.txt`, `tailor <URL>`, or `cat jd.txt | tailor`.
- **4 Flexible Ways to Input Job Descriptions**:
  1. **URL**: Fetch and parse HTML to clean plaintext with standard library `urllib` & `html.parser`.
  2. **File**: Pass path to a text file containing the JD.
  3. **Multi-line Paste**: Use `--paste` (or run without arguments) and end input on a line with `END` or `Ctrl+D` (`Ctrl+Z` on Windows).
  4. **Piped Stdin**: Pipe JD directly from clipboard or file (`cat jd.txt | tailor`, `pbpaste | tailor`, `Get-Content jd.txt | tailor`).
- **Zero Heavy SDK Dependencies**: Built with 100% pure Python standard library (`urllib.request`, `json`, `difflib`, `unittest`). No `groq` SDK, no `requests`, no heavy dependencies required.
- **Built-in Diff View (`--diff`)**: View clean, colored unified diffs of changes made to your resume directly in the terminal before saving.
- **Resilient API Client**: Automatic retry with exponential backoff for transient network errors and rate limits (`HTTP 429`, `500`, `502`, `503`, `504`).
- **Provider Agnostic (`--api-base`)**: While optimized for Groq, it supports any OpenAI-compatible API endpoint (Ollama, vLLM, OpenAI, OpenRouter).
- **Structure-Preserving AI**: Strictly preserves document classes, geometry, packages, fonts, custom commands, and macros. Only enhances bullet point wording, ATS keyword relevance, and skills prioritization.
- **Truthful & Grounded**: Hardcoded system prompt guarantees the model never hallucinates employers, dates, degrees, or fabricated metrics.
- **Automatic Multi-Engine PDF Compilation**: Automatically detects `latexmk`, `pdflatex`, or `xelatex` for clean PDF generation.

---

## 🚀 Quick Start & Installation

### 1. Requirements
- **Python 3.9+** (zero third-party packages required).
- A **Groq API Key** (free tier available at [console.groq.com](https://console.groq.com/keys)).
- *(Optional)* A LaTeX distribution (`pdflatex`, `latexmk`, or `xelatex`) if you want automatic local PDF compilation.

### 2. Clone Repository
```bash
git clone https://github.com/Chinmay0608/Builder.git
cd Builder
```

### 3. Install via pip (Optional)
You can install the CLI globally or in your virtual environment:
```bash
pip install -e .
```
This registers the `tailor` and `resume-tailor` console commands directly on your system `PATH`.

### 4. Configure via Setup Wizard
Run the one-time interactive setup wizard:
```bash
python tailor.py --setup
# or if installed via pip:
tailor --setup
```

The wizard prompts for:
1. **Master `.tex` Resume Path** (e.g. `examples/sample_resume.tex`)
2. **Groq API Key** (automatically loads from your `.env` file if present)
3. **Model Name** (default: `llama-3.3-70b-versatile`)
4. **Output Directory** (default: `./tailored_resumes`)
5. **Auto Compile to PDF** (`y/N`)

Settings are stored securely at `~/.resume_tailor/config.json` with restrictive `0600` permissions (owner read/write only).

---

## 💻 Input Modes & Usage Examples

### 1. Job Description from a URL
```bash
python tailor.py "https://boards.greenhouse.io/company/jobs/12345"
```
*Note: The tool strips HTML tags and scripts using standard library `html.parser`. If a job board requires JavaScript to render, paste the job description text manually.*

### 2. Job Description from a File
```bash
python tailor.py jd.txt
```

### 3. Multi-line Interactive Paste (`--paste` or no arguments)
```bash
python tailor.py --paste
# or simply:
python tailor.py
```
Paste any multi-line text into your terminal, then type `END` on a new line and press Enter (or press `Ctrl+D` / `Ctrl+Z` + Enter).

### 4. Piped Stdin (Clipboard or File)
```bash
# macOS clipboard:
pbpaste | python tailor.py

# Linux / WSL:
cat jd.txt | python tailor.py

# Windows PowerShell:
Get-Content jd.txt | python tailor.py
```

### 5. Review Changes with Built-in Diff (`--diff`)
```bash
python tailor.py jd.txt --diff
```
Prints an instant colored unified diff showing exactly which bullet points and keywords were tailored.

### 6. Specifying Company & Role
Pass `-c` / `--company` and `-r` / `--role` to customize the output filename (e.g. `resume_Google_Senior_SWE.tex`) and give extra context to the AI:
```bash
python tailor.py jd.txt -c "Google" -r "Senior Backend Engineer" --diff
```

---

## 🔧 Standalone Core Engine: `resume_tailor.py`

`resume_tailor.py` is the canonical engine suitable for direct CLI usage, scripts, or CI/CD pipelines:

```bash
python resume_tailor.py \
  --resume examples/sample_resume.tex \
  --job jd.txt \
  --company "Stripe" \
  --role "Software Engineer" \
  --output tailored_resumes/resume_Stripe_SWE.tex \
  --diff \
  --compile
```

### CLI Reference

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--resume` | **(Required)** Master `.tex` file path | — |
| `--job` | Raw JD text OR path to `.txt` file | — |
| `--job-url` | URL to a job posting to fetch & parse | — |
| `--company` | Target company name | `""` |
| `--role` | Target role/title | `""` |
| `--output` | Destination `.tex` path | `{resume}_{company}_{role}.tex` |
| `--model` | Model name | `llama-3.3-70b-versatile` |
| `--diff` | Display unified diff between original and tailored resume | `False` |
| `--compile` | Compile output `.tex` to PDF using `latexmk`/`pdflatex`/`xelatex` | `False` |
| `--api-key` | API Key | `GROQ_API_KEY` env var / `.env` |
| `--api-base` | Custom OpenAI-compatible base URL | `https://api.groq.com/openai/v1/chat/completions` |

---

## 📊 Rate Limits, Token Budgets & Cost

- **Groq Free Tier Limits**:
  - `llama-3.3-70b-versatile`: ~6,000 Tokens Per Minute (TPM) and 30 Requests Per Minute (RPM).
  - A typical 1-page LaTeX resume + JD prompt consumes ~1,500–2,500 input tokens.
  - Resume Tailor has built-in retry with exponential backoff on `HTTP 429` rate limits.
- **Max Output Tokens (`max_tokens: 8192`)**:
  - The model output buffer is capped at 8,192 tokens, which is more than enough to output a full 1–2 page LaTeX document without truncation.
- **Cost**:
  - On Groq's free tier, requests cost **\$0.00**. On paid tiers, a typical resume tailoring call costs less than **\$0.002** (a fraction of a cent).
- **Tip for Very Long JDs**:
  - When copying large JDs, trim company perks, boilerplate EEO legal statements, and recruiter bios. Focusing on responsibilities and requirements produces the highest quality ATS match.

---

## 📁 Repository Structure

```text
Builder/
├── .env.example                # Example environment file template
├── .gitignore                  # Strict gitignore protecting .env and output files
├── LICENSE                     # MIT License
├── README.md                   # Complete documentation
├── pyproject.toml              # Packaging configuration & console scripts
├── resume_tailor.py            # Canonical core engine (API client, LaTeX validation, diff)
├── tailor.py                   # Lightweight wrapper with setup wizard & config
├── examples/
│   └── sample_resume.tex       # Clean, anonymized 1-page sample resume template
├── tests/
│   └── test_validation.py      # Unit tests for validation, parsing, and diff functions
└── job_toolkit/                # Autonomous Job Application Toolkit (Chinmay's workflow)
    ├── run.py                  # Interactive main menu for evaluation, tailoring & tracking
    ├── evaluate.py             # 100% local, instant JD qualification evaluator (0 API tokens)
    ├── tailor.py               # Groq-powered 1-page LaTeX tailor tied to profile.json
    ├── tracker.py              # CLI application tracker (applications.json)
    ├── profile.json            # Structured candidate profile & preferences
    └── requirements.txt        # Optional dependencies for openpyxl / xlsx export
```

### About `job_toolkit/`
The `job_toolkit/` folder contains a specialized, automated pipeline tailored for high-volume job applications:
- **`evaluate.py`**: Instant, rule-based job qualification evaluator (under 1 second, zero API tokens used) that calculates tech stack match %, flags hard blockers, and recommends resume versions.
- **`tracker.py`**: Local CLI application tracker persisting to `applications.json` with status updates (`Applied`, `Interviewing`, `Offer`, `Rejected`).
- **`run.py`**: Unified interactive terminal dashboard connecting evaluation, tailoring, and tracking.

---

## 🧪 Running Tests

Resume Tailor includes a unit test suite testing all pure validation functions (`braces_balanced`, `looks_like_latex`, `extract_latex`, `load_job_description`, and `print_diff`):

```bash
python -m unittest discover -s tests -v
```

All tests run using Python's standard `unittest` framework with zero external dependencies.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
