"""INOMICS conference scraper.

INOMICS is the largest economics conference aggregator. Their pages are
JS-heavy but the conference detail links follow a predictable pattern.
We fetch individual detail pages for structured metadata.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import unquote

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

            # Parse the concatenated text to extract name, location, dates
            name, listing_location, listing_start, listing_deadline = self._parse_listing_text(raw_text)

            # Fetch detail page for structured metadata
            conf = self._fetch_detail(name, link, listing_location, listing_start, listing_deadline)
            if conf:
                conferences.append(conf)

        return conferences

    def _parse_listing_text(self, raw: str) -> tuple[str, str, datetime | None, datetime | None]:
        """Parse INOMICS concatenated listing text into name, location, dates.

        Raw text looks like:
        "47th RSEP International Multidisciplinary ConferenceBetween15 Mayand16 May
         inBarcelona,SpainMay 16, 20268080Review of Socio-Economic Perspectives (RSEP)"

        Returns: (name, location, start_date, deadline)
        """
        # Remove "ConferencePosted X days ago" prefix
        text = re.sub(r"^ConferencePosted\s+\d+\s+\w+\s+ago\s*", "", raw).strip()

        # Extract location from "in City, Country" pattern
        location = ""
        loc_match = re.search(r"\bin\s*([A-Z][a-zA-Z\s,]+(?:Spain|Germany|France|Italy|UK|United Kingdom|Netherlands|Belgium|Switzerland|Austria|Sweden|Norway|Denmark|Portugal|Greece|Poland|Czech Republic|Ireland|Finland|Hungary|Romania|Croatia|Turkey|Cyprus|Luxembourg|Estonia|Latvia|Lithuania|Slovenia|Slovakia|Malta|Bulgaria|Iceland))", text)
        if loc_match:
            location = loc_match.group(1).strip().rstrip(",")

        # Extract dates from "Between DD Month and DD Month" pattern
        start_date = None
        date_match = re.search(r"Between\s*(\d{1,2}\s+\w+)\s*and\s*(\d{1,2}\s+\w+).*?(\d{4})", text)
        if date_match:
            start_str = f"{date_match.group(1)} {date_match.group(3)}"
            start_date = self._parse_date(start_str)

        # Extract deadline from date patterns after the location
        deadline = None
        deadline_match = re.search(r"(\w+\s+\d{1,2},?\s+\d{4})", text)
        if deadline_match:
            deadline = self._parse_date(deadline_match.group(1))

        # Extract clean name — cut at "Between" or first date pattern
        name = re.split(r"Between\s*\d", text, maxsplit=1)[0].strip()
        if name == text:
            name = re.split(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, maxsplit=1)[0].strip()
        if name == text:
            name = re.split(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}", text, maxsplit=1)[0].strip()

        if len(name) < 10:
            name = raw

        return name, location, start_date, deadline

    def _fetch_detail(
        self, name: str, url: str,
        listing_location: str = "",
        listing_start: datetime | None = None,
        listing_deadline: datetime | None = None,
    ) -> Conference | None:
        """Fetch an INOMICS conference detail page for structured data."""
        try:
            resp = self.fetch(url)
        except Exception as e:
            logger.debug(f"[INOMICS] Detail fetch failed for {url}: {e}")
            return Conference(
                name=name,
                url=url,
                source=self.SOURCE_NAME,
                start_date=listing_start,
                deadline=listing_deadline,
                location=listing_location,
                phd_friendly=True,
            )

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to get a better title from the detail page <h1>
        title_el = soup.select_one("h1")
        if title_el:
            detail_name = title_el.get_text(strip=True)
            if 10 <= len(detail_name) <= 200:
                name = detail_name

        # Extract location from detail page
        location = ""
        for sel in [".location", ".field-location", "span[class*='location']",
                    "div[class*='location']", ".venue"]:
            el = soup.select_one(sel)
            if el:
                location = el.get_text(strip=True)
                break
        if not location:
            body_text = soup.get_text()
            loc_match = re.search(r"(?:Location|Venue|Place)[:\s]+([A-Z][^\n]{3,50})", body_text)
            if loc_match:
                location = loc_match.group(1).strip().rstrip(".")

        # Clean URL-encoded artifacts from location (e.g. "Sevilla%2C%20SpainSevilla , Spain")
        if location:
            decoded = unquote(location)
            # If URL-decoded version differs, the text has encoded parts — remove them
            if decoded != location:
                location = decoded
            # Remove duplicated text (encoded + decoded appearing together)
            # Pattern: "City%2C%20CountryCity , Country" → "City, Country"
            if "%" in location:
                location = unquote(location)
            # Check for doubled location text
            half = len(location) // 2
            if half > 5:
                first_half = location[:half].strip().rstrip(",").strip()
                second_half = location[half:].strip().lstrip(",").strip()
                # If the two halves are similar, keep just the second (cleaner) one
                if first_half.replace(" ", "").lower()[:10] == second_half.replace(" ", "").lower()[:10]:
                    location = second_half

        # Fall back to listing location if detail page didn't have one
        if not location and listing_location:
            location = listing_location

        # Extract dates from detail page
        start_date = None
        deadline = None
        body_text = soup.get_text(" ", strip=True)

        for pattern in [
            r"Between\s*(\d{1,2}\s+\w+)\s*and\s*\d{1,2}\s+\w+.*?(\d{4})",
            r"(?:Date|Event|Conference date|When)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:Date|Event|Conference date|When)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        ]:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                date_str = m.group(1)
                if m.lastindex and m.lastindex >= 2:
                    date_str += f" {m.group(2)}"
                start_date = self._parse_date(date_str)
                if start_date:
                    break

        for pattern in [
            r"(?:Deadline|Submission deadline|Application deadline)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"(?:Deadline|Submission deadline|Application deadline)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        ]:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                deadline = self._parse_date(m.group(1))
                if deadline:
                    break

        # Fall back to listing-extracted dates
        if not start_date and listing_start:
            start_date = listing_start
        if not deadline and listing_deadline:
            deadline = listing_deadline

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
