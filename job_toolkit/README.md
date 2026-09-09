# Chinmay's Job Toolkit

A streamlined, high-speed CLI toolkit built for Chinmay Maheshwari to evaluate job postings, generate tailored LaTeX resumes using Groq AI, and track applications in one centralized dashboard.

---

## Setup

1. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Groq API Key (Already configured via `.env`):**
   The toolkit automatically detects your `GROQ_API_KEY` from your `.env` file in the project folder!
   
   If setting on a new machine:
   - **Windows (PowerShell):**
     ```powershell
     $env:GROQ_API_KEY="your_api_key_here"
     ```
   - **Windows (CMD):**
     ```cmd
     set GROQ_API_KEY=your_api_key_here
     ```
   - **Linux / macOS:**
     ```bash
     export GROQ_API_KEY="your_api_key_here"
     ```
   - **Or via `.env` file:**
     ```env
     GROQ_API_KEY=your_key_here
     ```

*(Note: `evaluate.py` runs 100% locally and never requires an API key!)*

---

## Usage

### 🚀 Main Interactive Menu
```bash
python run.py
```
Presents a single clean terminal menu:
```
═══════════════════════════════════════
  CHINMAY'S JOB TOOLKIT
═══════════════════════════════════════
  1. Evaluate a JD
  2. Tailor resume for a JD
  3. Evaluate + Tailor (do both)
  4. Track application
  5. View application stats
  6. Exit
═══════════════════════════════════════
```

### ⚡ Individual CLI Tools

#### 1. Evaluate a Job Description
Instant local verdict (APPLY / BORDERLINE / SKIP), stack match percentage, blocker checks, and recommended resume version:
```bash
python evaluate.py
# Or evaluate a saved file directly:
python evaluate.py jd.txt
# Or piped from clipboard / cat:
cat jd.txt | python evaluate.py
```

#### 2. Tailor a LaTeX Resume
Generates a strictly grounded, one-page LaTeX resume customized for the target JD using Groq AI:
```bash
python tailor.py
# Or with options:
python tailor.py jd.txt --company "Google" --version full_stack
```
Outputs are saved automatically to `output/Chinmay_Resume_[CompanyName].tex`.

#### 3. Track Applications
Manage and monitor your job hunt pipeline in `applications.json`:
```bash
python tracker.py add       # Log a new application
python tracker.py list      # View all applications in a formatted table
python tracker.py update    # Update application status (OA, Interview, Rejected, etc.)
python tracker.py stats     # View application count and response/reply rates
```

---

## Files

- `profile.json` — Single source of truth containing Chinmay's background, core stack, hard blockers, and projects.
- `evaluate.py` — High-speed local JD analyzer with blocker detection, stack scoring, and version recommendation.
- `tailor.py` — Groq AI LaTeX resume generator with strict truthfulness & formatting rules.
- `tracker.py` — Application manager storing data in `applications.json`.
- `run.py` — Unified interactive entry point.
- `applications.json` — Auto-created database tracking all your applications and response stages.
- `output/` — Destination folder where all tailored `.tex` files are saved.
