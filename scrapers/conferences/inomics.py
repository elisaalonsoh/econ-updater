"""INOMICS conference scraper.

INOMICS is the largest economics conference aggregator. Their pages are
JS-heavy but the conference detail links follow a predictable pattern.
We fetch individual detail pages for structured metadata.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Conference

logger = logging.getLogger(__name__)


class INOMICSScraper(BaseScraper):
    SOURCE_NAME = "INOMICS"
    BASE_URL = "https://inomics.com"

    # Pages that list conferences
    LISTING_URLS = [
        "https://inomics.com/top/conferences",
        "https://inomics.com/search?conference=conference&discipline=economics",
    ]

    def scrape_conferences(self) -> list[Conference]:
        conferences = []

        for url in self.LISTING_URLS:
            try:
                resp = self.fetch(url)
                page_confs = self._parse_listing(resp.text)
                conferences.extend(page_confs)
            except Exception as e:
                logger.warning(f"[INOMICS] Failed to fetch {url}: {e}")
                continue

        # Deduplicate by normalized name
        seen_names: set[str] = set()
        seen_urls: set[str] = set()
        unique = []
        for c in conferences:
            norm = c.name.lower().strip()
            if norm not in seen_names and c.url not in seen_urls:
                seen_names.add(norm)
                seen_urls.add(c.url)
                unique.append(c)

        logger.info(f"[INOMICS] Found {len(unique)} conferences/events")
        return unique

    def _parse_listing(self, html: str) -> list[Conference]:
        conferences = []
        soup = BeautifulSoup(html, "html.parser")

        # Collect unique conference detail URLs
        seen_hrefs: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/conference/" not in href:
                continue
            link = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            if link in seen_hrefs:
                continue
            seen_hrefs.add(link)

            # Try to get a clean name from the link text
            raw_text = a.get_text(strip=True)
            if len(raw_text) < 10:
                continue

            # Parse the concatenated text to extract just the conference name
            name = self._clean_name(raw_text)

            # Fetch detail page for structured metadata
            conf = self._fetch_detail(name, link)
            if conf:
                conferences.append(conf)

        return conferences

    def _clean_name(self, raw: str) -> str:
        """Extract just the conference name from INOMICS concatenated text.

        Raw text looks like:
        "47th RSEP International Multidisciplinary ConferenceBetween15 Mayand16 May
         inBarcelona,SpainMay 16, 20268080Review of Socio-Economic Perspectives (RSEP)"
        """
        # Remove "ConferencePosted X days ago" prefix
        name = re.sub(r"^ConferencePosted\s+\d+\s+\w+\s+ago\s*", "", raw).strip()

        # Cut at "Between" which starts the date metadata
        name = re.split(r"Between\d", name, maxsplit=1)[0].strip()

        # Cut at date patterns like "May 16, 2026" or "15 May 2026"
        name = re.split(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", name, maxsplit=1)[0].strip()
        name = re.split(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}", name, maxsplit=1)[0].strip()

        # Cut at "Deadline:" or "Application deadline"
        name = re.split(r"(?:Deadline|Application deadline)", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()

        return name if len(name) >= 10 else raw

    def _fetch_detail(self, name: str, url: str) -> Conference | None:
        """Fetch an INOMICS conference detail page for structured data."""
        try:
            resp = self.fetch(url)
        except Exception as e:
            logger.debug(f"[INOMICS] Detail fetch failed for {url}: {e}")
            return Conference(
                name=name,
                url=url,
                source=self.SOURCE_NAME,
                phd_friendly=True,
            )

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to get a better title from the detail page
        title_el = soup.select_one("h1, .page-title, .conference-title")
        if title_el:
            detail_name = title_el.get_text(strip=True)
            if len(detail_name) >= 10:
                name = detail_name

        # Extract location
        location = ""
        for sel in [".location", ".field-location", "span[class*='location']",
                    "div[class*='location']", ".venue"]:
            el = soup.select_one(sel)
            if el:
                location = el.get_text(strip=True)
                break
        if not location:
            # Try to find text containing city/country patterns
            body_text = soup.get_text()
            loc_match = re.search(r"(?:Location|Venue|Place)[:\s]+([A-Z][^\n]{3,50})", body_text)
            if loc_match:
                location = loc_match.group(1).strip().rstrip(".")

        # Extract dates
        start_date = None
        deadline = None
        body_text = soup.get_text(" ", strip=True)

        # Look for event dates
        for pattern in [
            r"(?:Date|Event|Conference date|When)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:Date|Event|Conference date|When)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
            r"Between\s*(\d{1,2}\s+\w+)\s*and\s*\d{1,2}\s+\w+.*?(\d{4})",
        ]:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                date_str = m.group(1)
                if m.lastindex and m.lastindex >= 2:
                    date_str += f" {m.group(2)}"
                start_date = self._parse_date(date_str)
                if start_date:
                    break

        # Look for deadline
        for pattern in [
            r"(?:Deadline|Submission deadline|Application deadline)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:Deadline|Submission deadline|Application deadline)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        ]:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                deadline = self._parse_date(m.group(1))
                if deadline:
                    break

        # Description
        description = ""
        for sel in [".description", ".field-body", ".abstract", ".summary",
                    "div[class*='description']", "article p"]:
            el = soup.select_one(sel)
            if el:
                description = el.get_text(strip=True)[:300]
                break

        return Conference(
            name=name,
            url=url,
            source=self.SOURCE_NAME,
            start_date=start_date,
            deadline=deadline,
            location=location,
            description=description,
            phd_friendly=True,
        )

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None
        text = text.strip().rstrip(".")
        formats = [
            "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%B %d %Y",
            "%b %d, %Y", "%b %d %Y", "%Y-%m-%d", "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
