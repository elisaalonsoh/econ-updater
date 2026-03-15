# Econ Updater

Automated weekly digest of economics working papers and European conferences, scored for relevance to your research profile using an LLM.

## What it does

Every Monday at 08:30 CET, this tool:

1. **Scrapes working papers** from NBER, arXiv (econ), CEPR, IZA, and Fed banks
2. **Scrapes conferences** from INOMICS, WikiCFP, conference-service.com, EEA/RES, and NBER
3. **Scores relevance** using Claude Haiku against your research profile (keyword pre-filter + LLM batch scoring)
4. **Sends an HTML email digest** with papers grouped by relevance tier (Must Read / Should Read / Worth a Look) and upcoming conferences with structured metadata

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

### 3. Set environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Claude (relevance scoring) |
| `RESEND_API_KEY` | API key from [Resend](https://resend.com) (free tier, email sending) |
| `RECIPIENT_EMAIL` | Your email address |

### 4. Run locally

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

The included workflow at `.github/workflows/weekly_digest.yml` runs every Monday at 07:30 UTC (08:30 CET).

Add these as **repository secrets** (Settings → Secrets and variables → Actions):
- `ANTHROPIC_API_KEY`
- `RESEND_API_KEY`
- `RECIPIENT_EMAIL`

You can also trigger a run manually from the Actions tab via **workflow_dispatch**.

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
    └── weekly_digest.yml    # Cron schedule
```
