# job-tracker

A local Python CLI tool that analyzes your Gmail account to find all job applications
you have sent since a given start date, and shows which companies have responded.

**Runs entirely on your machine.** No data leaves except the Gmail API calls and
(optionally) a Groq API call for company/role extraction.

---

## Features

- **Gmail API via OAuth2** — read-only scope, no password needed
- **Application signals** — catches ATS confirmation emails (Greenhouse, Lever,
  Workday, iCIMS, SmartRecruiters, Superset, Jobvite, etc.) and subject-line patterns
- **Response signals** — detects interview invites, assessments, shortlists, offers,
  and rejections from recruiter emails and placement mailing lists
- **Groq LLM fallback** — when regex cannot extract company/role, falls back to
  `llama-3.3-70b-versatile` via your existing `GROQ_API_KEY`
- **Disk cache** — API responses cached under `./cache/` keyed by query hash;
  re-runs are instant
- **CSV + HTML output** — `./output/applications_YYYYMMDD_YYYYMMDD.csv` and
  optional `--html` report with status badges
- **Rate-limit aware** — exponential backoff on HTTP 429/5xx
- **Unit tested** — 12 pytest tests, zero live API calls in tests

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or, if you have `uv`:

```bash
uv pip install -r requirements.txt
```

### 2. Set up Gmail API credentials (one-time)

1. Go to <https://console.cloud.google.com/>
2. Create or select a project
3. **Enable Gmail API** → APIs & Services → Library → search "Gmail API" → Enable
4. **Create credentials** → APIs & Services → Credentials → Create Credentials
   → OAuth client ID → **Desktop app** → Download JSON
5. Save the downloaded file as **`credentials.json`** in this directory
6. **OAuth consent screen** → add your Gmail address as a Test User
   (required while the app is in "Testing" mode)

> The first run opens a browser window for you to grant consent.
> The token is cached at `~/.job_tracker/token.json` (mode 0600) and reused silently.

### 3. Set your Groq API key (optional but recommended)

Add to `d:\Resume Builder\.env` (already gitignored):

```
GROQ_API_KEY=gsk_...
```

The tool loads `.env` automatically.

### 4. Run

```bash
# From d:\Resume Builder\job-tracker\
python -m job_tracker.cli --since 2025-01-01

# With HTML report
python -m job_tracker.cli --since 2025-01-01 --html

# Skip cache (fresh fetch)
python -m job_tracker.cli --since 2025-01-01 --no-cache

# Disable LLM fallback
python -m job_tracker.cli --since 2025-01-01 --no-llm
```

---

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--since YYYY-MM-DD` | `2025-01-01` | Start date for search |
| `--email EMAIL` | — | Gmail address hint (informational only) |
| `--credentials PATH` | `./credentials.json` | Path to OAuth credentials JSON |
| `--no-cache` | — | Skip reading/writing disk cache |
| `--no-llm` | — | Disable Groq LLM fallback |
| `--html` | — | Also write an HTML report |
| `--output-dir DIR` | `./output` | Directory for CSV/HTML output |

---

## Output

### Terminal summary

```
==============================================================
  JOB APPLICATION TRACKER  --  42 application(s) found
==============================================================

📅 Interview  (3)
--------------------------------------------------
  2025-03-12  Stripe                        Software Engineer, Backend
  2025-02-28  Razorpay                      Data Analyst

📝 Assessment  (5)
...

❌ Rejected  (12)
...
```

### CSV

`output/applications_20250101_20250910.csv`

| company | role | date_applied | status | last_updated | source_email_id |
|---------|------|-------------|--------|--------------|----------------|
| Stripe | Software Engineer | 2025-02-10 | interview_invited | 2025-03-12 | msg001 |

### HTML

`output/applications_20250101_20250910.html` — open in any browser.

---

## Status Tags

| Tag | Meaning |
|-----|---------|
| `offer` | 🎉 Job offer received |
| `interview_invited` | 📅 Interview / call invited |
| `assessment_invited` | 📝 Coding test / OA |
| `shortlisted` | ✅ Shortlisted for next round |
| `rejected` | ❌ Rejection email |
| `no_response` | ⏳ No response email found |

---

## Project Structure

```
job-tracker/
  job_tracker/
    __init__.py        # package
    auth.py            # OAuth2 flow, token caching
    gmail_client.py    # Gmail API search + fetch, cache, backoff
    extract.py         # Company/role/date extraction (regex + Groq fallback)
    classify.py        # Response-type classification (keyword-based)
    report.py          # CSV + terminal + HTML output
    cli.py             # argparse entry point
  tests/
    fixtures/
      sample_emails.py # Fixture email dicts (no API calls)
    test_extract.py    # 8 unit tests for extract.py
    test_classify.py   # 7 unit tests for classify.py
  companies.yaml       # User-editable ATS domains / portal patterns
  credentials.json.example  # Template (copy to credentials.json)
  requirements.txt
  pyproject.toml
  .gitignore
  README.md
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

All tests use fixture emails — no Gmail API or Groq API calls.

---

## Cache

API responses are cached under `./cache/<query-hash>.json`.
Delete the `cache/` directory or pass `--no-cache` to force a fresh fetch.

---

## Privacy & Security

- OAuth token is stored at `~/.job_tracker/token.json` (Unix mode 0600).
- `credentials.json` and `token.json` are gitignored.
- Only **read-only** Gmail scope is requested — the tool cannot send, delete, or modify email.
- `cache/` and `output/` are gitignored — no email content is committed.

---

## Groq LLM Details

The LLM fallback uses `llama-3.3-70b-versatile` at `api.groq.com`.
It is called **only** when regex extraction cannot determine the company or role.
The system prompt instructs the model to return only a JSON object — no markdown, no explanation.
Fallback respects rate limits (exponential backoff, 3 retries max).
