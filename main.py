#!/usr/bin/env python3
"""Econ Updater — Weekly economics research digest.

Scrapes working papers and conferences, scores relevance with an LLM,
and sends a formatted email digest.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from digest.builder import build_digest
from email_sender import send_digest
from scorer import score_papers_with_llm
from scrapers.base import Paper, Conference

# Paper scrapers
from scrapers.papers.nber import NBERScraper
from scrapers.papers.arxiv_econ import ArxivEconScraper
from scrapers.papers.cepr import CEPRScraper
from scrapers.papers.iza import IZAScraper
from scrapers.papers.fed_banks import FedBanksScraper

# Conference scrapers
from scrapers.conferences.inomics import INOMICSScraper
from scrapers.conferences.wikicfp import WikiCFPScraper
from scrapers.conferences.eea import EEAScraper
from scrapers.conferences.confservice import ConfServiceScraper
from scrapers.conferences.nber_conf import NBERConfScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PAPER_SCRAPERS = {
    "nber": NBERScraper,
    "arxiv_econ": ArxivEconScraper,
    "cepr": CEPRScraper,
    "iza": IZAScraper,
    "fed_banks": FedBanksScraper,
}

CONFERENCE_SCRAPERS = {
    "inomics": INOMICSScraper,
    "wikicfp": WikiCFPScraper,
    "eea": EEAScraper,
    "confservice": ConfServiceScraper,
    "nber_conf": NBERConfScraper,
}


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_seen(path: str = "data/seen.json") -> set[str]:
    """Load previously seen paper/conference IDs to avoid duplicates."""
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set[str], path: str = "data/seen.json") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def scrape_papers(config: dict) -> list[Paper]:
    """Run all configured paper scrapers."""
    all_papers = []
    sources = config.get("paper_sources", list(PAPER_SCRAPERS.keys()))
    lookback = config.get("lookback_days", 8)

    for source_name in sources:
        scraper_cls = PAPER_SCRAPERS.get(source_name)
        if not scraper_cls:
            logger.warning(f"Unknown paper source: {source_name}")
            continue

        logger.info(f"Scraping papers from {source_name}...")
        try:
            scraper = scraper_cls(config)
            papers = scraper.scrape_papers(lookback_days=lookback)
            all_papers.extend(papers)
        except Exception as e:
            logger.error(f"Failed to scrape {source_name}: {e}")
            continue

    # Deduplicate across sources (same paper on NBER and CEPR)
    seen_titles = {}
    unique = []
    for p in all_papers:
        norm_title = p.title.lower().strip()
        if norm_title not in seen_titles:
            seen_titles[norm_title] = p
            unique.append(p)

    logger.info(f"Total papers: {len(all_papers)}, unique: {len(unique)}")
    return unique


def scrape_conferences(config: dict) -> list[Conference]:
    """Run all configured conference scrapers."""
    all_confs = []
    sources = config.get("conference_sources", list(CONFERENCE_SCRAPERS.keys()))

    for source_name in sources:
        scraper_cls = CONFERENCE_SCRAPERS.get(source_name)
        if not scraper_cls:
            logger.warning(f"Unknown conference source: {source_name}")
            continue

        logger.info(f"Scraping conferences from {source_name}...")
        try:
            scraper = scraper_cls(config)
            confs = scraper.scrape_conferences()
            all_confs.extend(confs)
        except Exception as e:
            logger.error(f"Failed to scrape {source_name}: {e}")
            continue

    # Deduplicate across sources by normalized name
    seen_names: set[str] = set()
    unique = []
    for c in all_confs:
        norm = c.name.lower().strip()
        if norm not in seen_names:
            seen_names.add(norm)
            unique.append(c)

    logger.info(f"Total conferences: {len(all_confs)}, unique: {len(unique)}")
    return unique


def run(
    config_path: str = "config.yaml",
    dry_run: bool = False,
    save_html: bool = False,
) -> None:
    """Main entry point."""
    config = load_config(config_path)
    seen = load_seen()

    # 1. Scrape
    logger.info("=" * 60)
    logger.info("STEP 1: Scraping papers...")
    papers = scrape_papers(config)

    logger.info("STEP 1b: Scraping conferences...")
    conferences = scrape_conferences(config)

    # 2. Filter out previously seen
    new_papers = [p for p in papers if p.id not in seen]
    new_confs = [c for c in conferences if c.id not in seen]
    logger.info(f"New papers: {len(new_papers)}, new conferences: {len(new_confs)}")

    # 3. Score relevance
    logger.info("=" * 60)
    logger.info("STEP 2: Scoring paper relevance...")
    scored_papers = score_papers_with_llm(new_papers, config)

    # 4. Build digest
    logger.info("=" * 60)
    logger.info("STEP 3: Building digest...")
    subject, html_body = build_digest(scored_papers, new_confs, config)

    # 5. Save HTML preview
    if save_html or dry_run:
        preview_path = Path("data/preview.html")
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(html_body)
        logger.info(f"Preview saved to {preview_path}")

    # 6. Send email
    if not dry_run:
        logger.info("STEP 4: Sending email...")
        success = send_digest(subject, html_body, config)
        if success:
            # Update seen set
            for p in new_papers:
                seen.add(p.id)
            for c in new_confs:
                seen.add(c.id)
            save_seen(seen)
            logger.info("Done! Digest sent and seen list updated.")
        else:
            logger.error("Failed to send email. Seen list NOT updated.")
            sys.exit(1)
    else:
        logger.info("Dry run complete. No email sent.")


def main():
    parser = argparse.ArgumentParser(description="Econ Updater — Weekly Research Digest")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and build digest but don't send email",
    )
    parser.add_argument(
        "--save-html",
        action="store_true",
        help="Save HTML preview to data/preview.html",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file",
    )
    args = parser.parse_args()

    run(
        config_path=args.config,
        dry_run=args.dry_run,
        save_html=args.save_html,
    )


if __name__ == "__main__":
    main()
