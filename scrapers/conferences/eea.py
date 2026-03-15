"""European economics conference scrapers.

Scrapes EEA, RES, EALE, and other key European conference sources.
Uses multiple URL patterns since these sites restructure periodically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)

# Multiple URL patterns per source (sites restructure over time)
CONFERENCE_PAGES = [
    {
        "name": "EEA",
        "urls": [
            "https://www.eeassoc.org/events",
            "https://www.eeassoc.org/congress",
            "https://eeassoc.org/events",
        ],
    },
    {
        "name": "RES",
        "urls": [
            "https://res.org.uk/events/",
            "https://www.res.org.uk/events/",
            "https://res.org.uk/event/",
        ],
    },
    {
        "name": "EALE",
        "urls": [
            "https://eale.nl/conferences/",
            "https://www.eale.nl/conferences/",
            "https://eale.nl/conference/",
            "https://www.eale.nl/",
        ],
    },
]


class EEAScraper(BaseScraper):
    SOURCE_NAME = "EEA/European"

    def scrape_conferences(self) -> list[Conference]:
        conferences = []

        for source in CONFERENCE_PAGES:
            found = False
            for url in source["urls"]:
                if found:
                    break
                try:
                    resp = self.fetch(url)
                    page_confs = self._parse_events_page(
                        resp.text, source["name"], url
                    )
                    if page_confs:
                        conferences.extend(page_confs)
                        found = True
                except Exception as e:
                    logger.debug(f"[{source['name']}] URL {url} failed: {e}")
                    continue

            if not found:
                logger.info(f"[{source['name']}] No working URL found — skipping")

        # Deduplicate by normalized name
        seen_names: set[str] = set()
        unique = []
        for c in conferences:
            norm = c.name.lower().strip()
            if norm not in seen_names:
                seen_names.add(norm)
                unique.append(c)

        logger.info(f"[EEA/European] Found {len(unique)} conferences (deduped from {len(conferences)})")
        return unique

    def _parse_events_page(
        self, html: str, source_name: str, base_url: str
    ) -> list[Conference]:
        conferences = []
        soup = BeautifulSoup(html, "html.parser")
        now = datetime.now(timezone.utc)

        # Generic event parsing — try many selectors
        for el in soup.select(
            "article, .event-item, .event, .conference-item, "
            ".views-row, li.event, div.event-card, .listing-item, "
            "div[class*='event'], div[class*='conference'], "
            ".card, .post-item, .entry"
        ):
            try:
                title_el = el.select_one(
                    "h2 a, h3 a, h4 a, .event-title a, a[class*='title'], "
                    ".title a, a.card-title"
                )
                if not title_el:
                    continue

                name = title_el.get_text(strip=True)
                if len(name) < 5:
                    continue

                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = urljoin(base_url, link)

                # Date
                date_el = el.select_one(
                    "time, .date, .event-date, span[class*='date'], "
                    "div[class*='date']"
                )
                date_text = date_el.get_text(strip=True) if date_el else ""
                start_date = self._parse_date(date_text)

                # Location
                loc_el = el.select_one(
                    ".location, .event-location, .venue, span[class*='location']"
                )
                location = loc_el.get_text(strip=True) if loc_el else ""

                # Description
                desc_el = el.select_one(
                    ".description, .event-description, .summary, p, .excerpt"
                )
                description = desc_el.get_text(strip=True) if desc_el else ""

                if start_date and start_date < now:
                    continue

                conferences.append(Conference(
                    name=name,
                    url=link,
                    source=f"{self.SOURCE_NAME} ({source_name})",
                    start_date=start_date,
                    location=location,
                    description=description,
                    phd_friendly=True,
                ))
            except Exception as e:
                logger.debug(f"[{source_name}] Skipping event: {e}")
                continue

        return conferences

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        text = text.strip()
        formats = [
            "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y",
            "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
