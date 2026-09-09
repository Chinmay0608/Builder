# Resume Tailor

A fast, lightweight command-line tool that tailors a LaTeX (`.tex`) resume for a specific job posting in **one single command** using the ultra-fast Groq API (`llama-3.3-70b-versatile`). It outputs the tailored LaTeX code directly to the console for quick copy-pasting (e.g. into Overleaf) and saves it to a `.tex` file (with optional automatic PDF compilation).

---

## ✨ Features

- **One-Command Workflow**: Once configured, tailor your resume by running `tailor jd.txt`, `tailor <URL>`, or `cat jd.txt | tailor`.
- **4 Flexible Ways to Input Job Descriptions**:
  1. **URL**: Fetch and strip HTML to plaintext automatically with Python standard library.
  2. **File**: Pass path to a text file containing the JD.
  3. **Multi-line Paste**: Use `--paste` (or run without arguments) and end input on a line with `END` or `Ctrl+D` (`Ctrl+Z` on Windows).
  4. **Piped Stdin**: Pipe JD directly from clipboard or file (`cat jd.txt | python tailor.py`, `pbpaste | python tailor.py`, `Get-Content jd.txt | python tailor.py`).
- **Zero Heavy SDK Dependencies**: Uses pure standard Python (`urllib.request` / `json`) to call Groq's OpenAI-compatible completions endpoint. No `groq` SDK required.
- **Structure-Preserving AI**: Strictly preserves document classes, geometry, packages, fonts, custom commands, and macros. Only edits content, bullet phrasing, ATS keywords, and skills prioritization.
- **Truthful & Grounded**: Prevents hallucinations — never invents dates, companies, degrees, or fabricated metrics.
- **Dual Output**: Prints the full tailored LaTeX directly to stdout (ready for Overleaf) and saves to disk.
- **Automatic PDF Generation**: Optionally compiles output twice using `pdflatex` for clean references.

---

## 🚀 Quick Start & Setup

### 1. Requirements
- **Python 3.9+**
- Optional: `pdflatex` (from TeX Live, MacTeX, or MiKTeX) for automatic PDF compilation.
- A **Groq API Key** (free tier available at [console.groq.com](https://console.groq.com/keys)).

### 2. Installation & Setup
Clone or download this repository:
```bash
git clone https://github.com/your-username/resume-tailor.git
cd resume-tailor
```

*(Optional)* Install `requests` if using in custom scripts (the tool uses standard library `urllib` by default):
```bash
pip install requests --break-system-packages
```

Run the one-time interactive setup wizard:
```bash
python tailor.py --setup
```

The wizard prompts for:
1. **Master `.tex` Resume Path** (e.g. `~/resumes/master.tex`)
2. **Groq API Key** (automatically loads from your `.env` file if present)
3. **Model Name** (default: `llama-3.3-70b-versatile`)
4. **Output Directory** (default: `./tailored_resumes`)
5. **Auto Compile to PDF** (`y/N`)

Settings are saved to `~/.resume_tailor/config.json`. Re-run `--setup` anytime to update settings.

---

## 💻 Input Modes & Usage Examples

### 1. Job Description from a URL
```bash
python tailor.py "https://boards.greenhouse.io/company/jobs/12345"
```
*Note: The tool strips HTML tags and scripts using standard library `html.parser`. If a site requires heavy JavaScript to render, paste the text manually.*

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

### 5. Specifying Company & Role
Pass `-c` / `--company` and `-r` / `--role` to customize the output filename (e.g. `master_Google_Senior_SWE.tex`) and give extra context to the AI:
```bash
python tailor.py jd.txt -c "Google" -r "Senior Backend Engineer"
```

### 6. Override Master Resume for a Single Run
```bash
python tailor.py jd.txt --new-resume path/to/other_resume.tex
```

---

## ⚡ Set Up a Shell Alias (Literally `tailor jd.txt`)

### Bash / Zsh (`~/.bashrc` or `~/.zshrc`)
```bash
alias tailor="python3 /path/to/tailor.py"
```
Reload your configuration:
```bash
source ~/.bashrc  # or source ~/.zshrc
```
Now tailor any resume with:
```bash
tailor jd.txt
cat jd.txt | tailor -c "Stripe" -r "Backend Lead"
tailor "https://jobs.lever.co/example/123"
```

### PowerShell (`$PROFILE`)
Add this function to your PowerShell profile:
```powershell
function tailor {
    python "D:\Resume Builder\tailor.py" @args
}
```
Reload profile:
```powershell
. $PROFILE
```

---

## 🔧 Core Engine: `resume_tailor.py`

`resume_tailor.py` is the standalone core engine suitable for direct CLI usage or CI/CD automation:

```bash
python resume_tailor.py \
  --resume master.tex \
  --job jd.txt \
  --company "Google" \
  --role "Senior Software Engineer" \
  --output tailored_resumes/master_Google_SWE.tex \
  --model "llama-3.3-70b-versatile" \
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
| `--model` | Groq model name | `llama-3.3-70b-versatile` |
| `--compile` | Compile output `.tex` to PDF with `pdflatex` | `False` |
| `--api-key` | Groq API Key | `GROQ_API_KEY` env var / `.env` |

---

## ⚠️ Important: Reviewing Output Diff

> [!IMPORTANT]
> **Always inspect the generated LaTeX diff before sending out your application!**
> 
> Compare your original resume against the tailored version:
> ```bash
> diff -u master.tex tailored_resumes/master_Google_SWE.tex
> # or with git:
> git diff --no-index master.tex tailored_resumes/master_Google_SWE.tex
> ```
> 
> While Resume Tailor enforces strict preservation of document macros and formatting, custom resume packages (like `moderncv`, `awesome-cv`, or custom `.cls` files) should always be verified to confirm no custom macro commands were modified.
