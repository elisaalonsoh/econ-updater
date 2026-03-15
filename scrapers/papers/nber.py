"""NBER working papers scraper using their RSS feed."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import feedparser

from scrapers.base import BaseScraper, Paper

logger = logging.getLogger(__name__)


class NBERScraper(BaseScraper):
    SOURCE_NAME = "NBER"
    RSS_URL = "https://www.nber.org/rss/new.xml"

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        papers = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        try:
            feed = feedparser.parse(self.RSS_URL)
        except Exception as e:
            logger.warning(f"[NBER] Failed to parse RSS: {e}")
            return papers

        for entry in feed.entries:
            try:
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if pub_date and pub_date < cutoff:
                    continue

                raw_title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "").strip()

                # NBER RSS titles often contain "-- by Author1, Author2"
                title = raw_title
                title_authors: list[str] = []
                for sep in [" -- by ", " —- by ", " — by ", " - by "]:
                    if sep in raw_title:
                        title, author_part = raw_title.split(sep, 1)
                        title = title.strip()
                        title_authors = [
                            a.strip() for a in author_part.split(",") if a.strip()
                        ]
                        break

                # NBER RSS also has author info in dc:creator or author field
                authors_raw = entry.get("author", "") or entry.get("dc_creator", "")
                authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
                # Prefer authors parsed from title if dc:creator is empty
                if not authors and title_authors:
                    authors = title_authors

                if not title or not link:
                    continue

                papers.append(Paper(
                    title=title,
                    authors=authors,
                    abstract=summary,
                    url=link,
                    source=self.SOURCE_NAME,
                    date=pub_date,
                ))
            except Exception as e:
                logger.debug(f"[NBER] Skipping entry: {e}")
                continue

        logger.info(f"[NBER] Found {len(papers)} papers")
        return papers
