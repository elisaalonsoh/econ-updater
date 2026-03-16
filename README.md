# Econ Updater

Automated weekly digest of economics working papers and European conferences, scored for relevance to your research profile using an LLM.

## What it does

Every Monday morning, this tool:

1. **Scrapes working papers** from NBER, arXiv (econ), CEPR, IZA, and Fed banks
2. **Scrapes conferences** from INOMICS, WikiCFP, conference-service.com, EEA/RES, and NBER
3. **Scores relevance** using Claude Haiku against your research profile (keyword pre-filter + LLM batch scoring)
4. **Sends an HTML email digest** with papers grouped by relevance tier (Must Read / Should Read) and upcoming conferences with structured metadata

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your research profile

Edit `config.yaml` to set your:
- Research profile description
- JEL codes (primary + adjacent)
- Keywords (strong + moderate signal)
- Paper and conference sources to scrape
- LLM model and relevance thresholds

### 3. Sign up for Resend (email sending)

This project uses [Resend](https://resend.com) to send the digest email. The free tier (100 emails/day) is more than enough.

1. Sign up at [resend.com](https://resend.com) — GitHub login works
2. Go to **API Keys** and create a new key
3. Copy the key — you'll need it as `RESEND_API_KEY` below

### 4. Set environment variables in Github

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Claude (relevance scoring) — [console.anthropic.com](https://console.anthropic.com) |
| `RESEND_API_KEY` | API key from Resend (see step 3 above) |
| `RECIPIENT_EMAIL` | Your email address |

### 5. Run locally

```bash
# Full run (scrape + score + send email)
python main.py

# Dry run (scrape + score, save HTML preview, no email)
python main.py --dry-run

# Save HTML preview alongside sending
python main.py --save-html
```

The HTML preview is saved to `data/preview.html`.

## GitHub Actions (automated weekly run)

The workflow at `.github/workflows/weekly_digest.yml` runs on demand via `workflow_dispatch`. Scheduling is handled externally by [cron-job.org](https://cron-job.org) (free), which calls the GitHub API to trigger the workflow on your chosen schedule. This is more reliable than GitHub's built-in cron scheduler.

### Step 1: Add repository secrets

Go to your repo → Settings → Secrets and variables → Actions, and add:
- `ANTHROPIC_API_KEY`
- `RESEND_API_KEY`
- `RECIPIENT_EMAIL`

### Step 2: Create a GitHub Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Click **Generate new token**, set expiration, and under **Repository access** select only this repo
3. Under **Permissions → Actions** set to **Read and write**
4. Click **Generate token** and copy the value (you only see it once)

### Step 3: Set up cron-job.org

1. Sign up free at [cron-job.org](https://cron-job.org)
2. Create a new cronjob with these settings:

| Field | Value |
|---|---|
| URL | `https://api.github.com/repos/YOUR_USERNAME/econ-updater/actions/workflows/weekly_digest.yml/dispatches` |
| Method | `POST` |
| Schedule | Your chosen day/time (e.g. Monday 08:00 UTC) |
| Header — Key: `Authorization` | Value: `Bearer YOUR_TOKEN` |
| Header — Key: `Accept` | Value: `application/vnd.github+json` |
| Header — Key: `Content-Type` | Value: `application/json` |
| Request body | `{"ref":"main"}` |

3. Use **Test run** to verify you get a `204 No Content` response — this means the workflow was triggered successfully

Previously seen papers are cached across runs using GitHub Actions cache (`data/seen.json`), so you won't get duplicates week to week.

## Project structure

```
├── main.py                  # Orchestrator
├── config.yaml              # Research profile and settings
├── scorer.py                # Keyword pre-filter + LLM relevance scoring
├── email_sender.py          # Resend API email sender
├── digest/
│   └── builder.py           # HTML email template builder
├── scrapers/
│   ├── base.py              # Paper/Conference dataclasses, base scraper
│   ├── papers/
│   │   ├── nber.py          # NBER working papers (RSS)
│   │   ├── arxiv_econ.py    # arXiv econ categories (API)
│   │   ├── cepr.py          # CEPR discussion papers (HTML)
│   │   ├── iza.py           # IZA discussion papers (HTML)
│   │   └── fed_banks.py     # Federal Reserve banks (RSS)
│   └── conferences/
│       ├── inomics.py       # INOMICS (HTML + detail pages)
│       ├── wikicfp.py       # WikiCFP
│       ├── eea.py           # EEA, RES, EALE
│       ├── confservice.py   # conference-service.com
│       └── nber_conf.py     # NBER conferences
└── .github/workflows/
    └── weekly_digest.yml    # Workflow (triggered via cron-job.org)
```
