"""Base scraper class and shared data models."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    """Normalize a paper title for dedup comparison."""
    t = title.lower()
    t = unicodedata.normalize("NFKD", t)
    # Unify dash-like characters to hyphen
    t = re.sub(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]", "-", t)
    # Strip punctuation that varies between sources
    t = re.sub(r"[\"'\u201c\u201d\u2018\u2019.,;:!?()\[\]{}]", "", t)
    # Collapse all whitespace to single space
    t = re.sub(r"\s+", " ", t)
    return t.strip()


@dataclass
class Paper:
    title: str
    authors: list[str]
    abstract: str
    url: str
    source: str
    date: Optional[datetime] = None
    jel_codes: list[str] = field(default_factory=list)
    relevance_score: Optional[float] = None

    @property
    def id(self) -> str:
        """Unique identifier for deduplication."""
        return f"{self.source}:{self.url}"

    @property
    def title_key(self) -> str:
        """Normalized title key for cross-source deduplication."""
        return f"title:{normalize_title(self.title)}"


@dataclass
class Conference:
    name: str
    url: str
    source: str
    deadline: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: str = ""
    description: str = ""
    phd_friendly: bool = True
    relevance_score: Optional[float] = None

    @property
    def id(self) -> str:
        return f"{self.source}:{self.url}"


class BaseScraper:
    """Base class for all scrapers."""

    SOURCE_NAME: str = "unknown"
    BASE_URL: str = ""

    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "EconUpdater/1.0 (academic research digest; "
                "https://github.com/swediot/econ-updater)"
            )
        })

    def fetch(self, url: str, **kwargs) -> requests.Response:
        """Fetch a URL with error handling and rate limiting."""
        try:
            resp = self.session.get(url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"[{self.SOURCE_NAME}] Failed to fetch {url}: {e}")
            raise

    def scrape_papers(self, lookback_days: int = 8) -> list[Paper]:
        raise NotImplementedError

    def scrape_conferences(self) -> list[Conference]:
        raise NotImplementedError
