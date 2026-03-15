"""Build the HTML email digest from scraped papers and conferences."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scrapers.base import Conference, Paper

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "email.html"


def build_digest(
    papers: list[Paper],
    conferences: list[Conference],
    config: dict,
) -> tuple[str, str]:
    """Build the email subject and HTML body.

    Returns:
        (subject, html_body)
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%d %B %Y")

    prefix = config.get("email", {}).get("subject_prefix", "[Econ Digest]")
    subject = f"{prefix} Week of {date_str}"

    min_score = config.get("llm", {}).get("min_relevance_score", 0.4)
    max_papers = config.get("llm", {}).get("max_papers_in_digest", 40)

    # Filter and sort papers by relevance
    scored_papers = [p for p in papers if (p.relevance_score or 0) >= min_score]
    scored_papers.sort(key=lambda p: p.relevance_score or 0, reverse=True)
    scored_papers = scored_papers[:max_papers]

    # Group papers by relevance tier
    must_read = [p for p in scored_papers if (p.relevance_score or 0) >= 0.7]
    should_read = [p for p in scored_papers if 0.5 <= (p.relevance_score or 0) < 0.7]
    might_read = [p for p in scored_papers if (p.relevance_score or 0) < 0.5]

    # Filter conferences:
    # - Exclude if deadline has already passed
    # - If deadline is TBA/missing, exclude if conference is less than 3 months away
    three_months = now + timedelta(days=90)
    filtered_confs = []
    for c in conferences:
        if c.deadline and c.deadline < now:
            continue  # deadline passed
        if not c.deadline:
            # No deadline — only keep if conference is 3+ months away (or no date known)
            if c.start_date and c.start_date < three_months:
                continue
        filtered_confs.append(c)

    # Sort by relevance (highest first)
    filtered_confs.sort(key=lambda c: c.relevance_score or 0, reverse=True)

    # Build HTML
    html = _render_html(
        date_str=date_str,
        must_read=must_read,
        should_read=should_read,
        might_read=might_read,
        conferences=filtered_confs,
        total_scraped=len(papers),
        total_shown=len(scored_papers),
    )

    return subject, html


def _render_html(
    date_str: str,
    must_read: list[Paper],
    should_read: list[Paper],
    might_read: list[Paper],
    conferences: list[Conference],
    total_scraped: int,
    total_shown: int,
) -> str:
    """Render the email HTML."""

    papers_html = ""

    if must_read:
        papers_html += _section_header("Must Read", "#c0392b", len(must_read))
        for p in must_read:
            papers_html += _paper_card(p, "#fdecea")

    if should_read:
        papers_html += _section_header("Should Read", "#e67e22", len(should_read))
        for p in should_read:
            papers_html += _paper_card(p, "#fef5e7")

    if might_read:
        papers_html += _section_header("Worth a Look", "#2980b9", len(might_read))
        for p in might_read:
            papers_html += _paper_card(p, "#eaf2f8")

    confs_html = ""
    if conferences:
        for c in conferences:
            confs_html += _conference_card(c)

    n_must = len(must_read)
    n_should = len(should_read)
    n_confs = len(conferences)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Econ Digest — {date_str}</title>
</head>
<body style="margin:0; padding:0; background-color:#f5f5f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5;">
<tr><td align="center" style="padding: 20px 10px;">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:8px; overflow:hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

<!-- Header -->
<tr><td style="background-color:#2c3e50; padding:24px 30px;">
  <h1 style="margin:0; color:#ffffff; font-size:22px; font-weight:600;">Econ Research Digest</h1>
  <p style="margin:6px 0 0; color:#bdc3c7; font-size:14px;">Week of {date_str}</p>
</td></tr>

<!-- Summary row -->
<tr><td style="padding:16px 30px; background-color:#f8f9fa; border-bottom:1px solid #e9ecef;">
  <table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td align="center" style="padding:8px;">
      <div style="font-size:24px; font-weight:700; color:#c0392b;">{n_must}</div>
      <div style="font-size:11px; color:#7f8c8d; text-transform:uppercase; letter-spacing:0.5px;">Must Read</div>
    </td>
    <td align="center" style="padding:8px;">
      <div style="font-size:24px; font-weight:700; color:#e67e22;">{n_should}</div>
      <div style="font-size:11px; color:#7f8c8d; text-transform:uppercase; letter-spacing:0.5px;">Should Read</div>
    </td>
    <td align="center" style="padding:8px;">
      <div style="font-size:24px; font-weight:700; color:#2980b9;">{n_confs}</div>
      <div style="font-size:11px; color:#7f8c8d; text-transform:uppercase; letter-spacing:0.5px;">Conferences</div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- Papers -->
<tr><td style="padding:20px 30px;">
  <h2 style="margin:0 0 16px; color:#2c3e50; font-size:18px; border-bottom:2px solid #3498db; padding-bottom:8px;">
    New Papers
  </h2>
  {papers_html if papers_html else '<p style="color:#7f8c8d;">No papers matched your research profile this week.</p>'}
</td></tr>

<!-- Conferences -->
<tr><td style="padding:0 30px 20px;">
  <h2 style="margin:0 0 16px; color:#2c3e50; font-size:18px; border-bottom:2px solid #2980b9; padding-bottom:8px;">
    Conferences
  </h2>
  {confs_html if confs_html else '<p style="color:#7f8c8d;">No new conferences found this week.</p>'}
</td></tr>

<!-- Footer -->
<tr><td style="background-color:#ecf0f1; padding:16px 30px; text-align:center;">
  <p style="margin:0; color:#7f8c8d; font-size:12px;">
    Generated by <strong>econ-updater</strong> &middot;
    Sources: NBER, arXiv, CEPR, IZA, Fed, INOMICS, WikiCFP, conference-service.com, EEA/RES
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _section_header(title: str, color: str, count: int) -> str:
    return f"""
    <div style="margin:16px 0 8px; padding:6px 12px; background-color:{color}; border-radius:4px; display:inline-block;">
      <span style="color:#ffffff; font-size:13px; font-weight:600;">{title} ({count})</span>
    </div>
    """


def _paper_card(paper: Paper, bg_color: str) -> str:
    authors_str = ", ".join(paper.authors[:4])
    if len(paper.authors) > 4:
        authors_str += f" + {len(paper.authors) - 4} more"

    score_str = f"{paper.relevance_score:.0%}" if paper.relevance_score else ""

    abstract_preview = paper.abstract[:300] if paper.abstract else ""
    if len(paper.abstract or "") > 300:
        abstract_preview += "..."

    return f"""
    <div style="margin:8px 0; padding:12px 16px; background-color:{bg_color}; border-radius:6px; border-left:3px solid #bdc3c7;">
      <a href="{paper.url}" style="color:#2c3e50; font-size:14px; font-weight:600; text-decoration:none; line-height:1.3;">
        {paper.title}
      </a>
      <div style="margin:4px 0; color:#7f8c8d; font-size:12px;">
        {authors_str}
        {f' &middot; {paper.source}' if paper.source else ''}
        {f' &middot; Relevance: {score_str}' if score_str else ''}
      </div>
      <p style="margin:6px 0 0; color:#555; font-size:12px; line-height:1.4;">
        {abstract_preview}
      </p>
    </div>
    """


_LOWERCASE_WORDS = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
                     "of", "with", "by", "from", "as", "is", "was", "are", "were"}


def _clean_conference_name(name: str) -> str:
    """Clean conference name: remove 'Call for Papers' etc., convert to title case."""
    # Remove common prefixes (case-insensitive)
    name = re.sub(
        r"^(?:call\s+for\s+(?:papers|applications|thematic\s+sessions)\s*[:\-–—.]?\s*)",
        "", name, flags=re.IGNORECASE
    ).strip()

    # Remove trailing " - Call for ..." suffixes
    name = re.sub(
        r"\s*[-–—]\s*call\s+for\s+(?:papers|applications|thematic\s+sessions).*$",
        "", name, flags=re.IGNORECASE
    ).strip()

    # Remove form label junk
    name = re.sub(r"(?:Email\s*Address|Full\s*Name).*$", "", name, flags=re.IGNORECASE).strip()

    # Fix title case: handle ALL CAPS and mixed-case issues like "5Th", "ON", "AND"
    words = name.split()
    result = []
    for i, w in enumerate(words):
        # Keep short all-caps words as acronyms (RSEP, IWH, NBP, CEPR, etc.)
        if len(w) <= 5 and w.isupper() and w.isalpha():
            result.append(w)
        # Fix ordinals like "5Th", "19Th" → "5th", "19th"
        elif re.match(r"^\d+[A-Z][a-z]+$", w):
            result.append(w.lower())
        # Fix ALL CAPS words or mixed-case junk
        elif w.isupper() and len(w) > 1:
            lower = w.lower()
            if i == 0:
                result.append(w.title())
            elif lower in _LOWERCASE_WORDS:
                result.append(lower)
            else:
                result.append(w.title())
        # Words with weird casing like "ON" in otherwise normal text
        elif w.upper() == w and len(w) > 1 and not w[0].isdigit():
            lower = w.lower()
            if lower in _LOWERCASE_WORDS and i > 0:
                result.append(lower)
            else:
                result.append(w.title())
        else:
            result.append(w)

    name = " ".join(result)
    return name


def _conference_card(conf: Conference) -> str:
    name = _clean_conference_name(conf.name)

    deadline_str = conf.deadline.strftime("%d %b %Y") if conf.deadline else ""
    date_str = ""
    if conf.start_date and conf.end_date:
        date_str = f"{conf.start_date.strftime('%d %b')} – {conf.end_date.strftime('%d %b %Y')}"
    elif conf.start_date:
        date_str = conf.start_date.strftime("%d %b %Y")

    score_str = f"{conf.relevance_score:.0%}" if conf.relevance_score else ""

    # Build metadata fields
    fields = []
    if conf.location:
        fields.append(f"<strong>Location:</strong> {conf.location}")
    if date_str:
        fields.append(f"<strong>Date:</strong> {date_str}")
    if deadline_str:
        fields.append(f"<strong>Deadline:</strong> {deadline_str}")
    else:
        fields.append("<strong>Deadline:</strong> TBA")
    if score_str:
        fields.append(f"<strong>Relevance:</strong> {score_str}")

    fields_html = " &middot; ".join(fields)

    return f"""
    <div style="margin:8px 0; padding:12px 16px; background-color:#eaf2f8; border-radius:6px; border-left:3px solid #2980b9;">
      <a href="{conf.url}" style="color:#2c3e50; font-size:14px; font-weight:600; text-decoration:none;">
        {name}
      </a>
      <div style="margin:4px 0; color:#7f8c8d; font-size:12px;">
        {fields_html}
      </div>
    </div>
    """
