"""CEPR Discussion Papers scraper via HTML page.

The CEPR RSS feed is defunct — we scrape the publications listing page directly.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Paper

logger = logging.getLogger(__name__)


class CEPRScraper(BaseScraper):
    SOURCE_NAME = "CEPR"
    LISTING_URL = "https://cepr.org/publications/discussion-papers"

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        papers = []

        try:
            resp = self.fetch(self.LISTING_URL)
        except Exception as e:
            logger.warning(f"[CEPR] Failed to fetch listings: {e}")
            return papers

        soup = BeautifulSoup(resp.text, "html.parser")

        # CEPR listing uses Drupal views-row divs
        for item in soup.select(".views-row, article"):
            try:
                title_el = item.select_one("h2 a, h3 a, h4 a, .title a")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                # Remove DP number prefix like "DP21294 "
                title = re.sub(r"^DP\d+\s*", "", title)

                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://cepr.org{link}"

                # Authors from listing: look for links to /about/people/
                authors: list[str] = []
                for a_tag in item.select("a[href*='/about/people/']"):
                    name = a_tag.get_text(strip=True)
                    if name and name not in authors:
                        authors.append(name)

                # Fallback: try generic author selectors
                if not authors:
                    author_el = item.select_one(
                        ".authors, .field-authors, span[class*='author']"
                    )
                    if author_el:
                        authors_raw = author_el.get_text(strip=True)
                        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

                # Get date
                date_el = item.select_one(
                    "time, .date, span[class*='date']"
                )
                pub_date = None
                if date_el:
                    date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
                    pub_date = self._parse_date(date_text)

                if not title or not link:
                    continue

                # Always fetch detail page for abstract (and authors if still missing)
                abstract = ""
                if link:
                    try:
                        detail_authors, detail_abstract = self._fetch_detail(link)
                        if not authors and detail_authors:
                            authors = detail_authors
                        if detail_abstract:
                            abstract = detail_abstract
                    except Exception as e:
                        logger.debug(f"[CEPR] Detail fetch failed for {link}: {e}")

                papers.append(Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=link,
                    source=self.SOURCE_NAME,
                    date=pub_date,
                ))
            except Exception as e:
                logger.debug(f"[CEPR] Skipping article: {e}")
                continue

        logger.info(f"[CEPR] Found {len(papers)} discussion papers")
        return papers

    def _fetch_detail(self, url: str) -> tuple[list[str], str]:
        """Fetch a CEPR detail page to extract authors and abstract."""
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Authors — CEPR uses links to /about/people/author-name
        authors: list[str] = []
        for a_tag in soup.select("a[href*='/about/people/']"):
            name = a_tag.get_text(strip=True)
            if name and name not in authors:
                authors.append(name)

        # Fallback selectors
        if not authors:
            for sel in [
                ".field--name-field-authors a",
                ".author-name",
                "div[class*='author'] a",
            ]:
                els = soup.select(sel)
                if els:
                    authors = [el.get_text(strip=True) for el in els if el.get_text(strip=True)]
                    break

        # Abstract — try specific selectors, then fall back to main content paragraphs
        abstract = ""
        for sel in [
            ".field--name-field-abstract",
            ".abstract",
            "div[class*='abstract']",
            ".field-body",
            ".paper-abstract",
        ]:
            el = soup.select_one(sel)
            if el:
                abstract = el.get_text(strip=True)
                break

        # Fallback: grab the first substantial <p> in the main content area
        if not abstract:
            for p in soup.select("article p, .content p, main p, .node__content p"):
                text = p.get_text(strip=True)
                if len(text) > 100:  # Skip short navigation text
                    abstract = text
                    break

        return authors, abstract

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip()
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
            "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
