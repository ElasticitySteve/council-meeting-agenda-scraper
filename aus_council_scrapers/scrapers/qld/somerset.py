"""Somerset publishes every agenda/minutes PDF as a flat link list inside
an OpenCities "document library" accordion, all on one single page -- no
pagination, no per-meeting detail pages. This is a different OpenCities
widget than gold_coast.py/moreton_bay.py's (confirmed directly: no
`.meeting-document` divs, no `.seamless-pagination` widget anywhere on the
page, only `.accordion-list-item-container` -- satisfies platforms.py's
OpenCities signature without matching either shared module's assumptions,
so this scraper is bespoke rather than reusing `_opencities_paging`/
`_opencities_detail`).

Somerset's own domain blocks DefaultFetcher's spoofed browser User-Agent
(403) but returns 200 for an honest one -- confirmed directly, same as
brisbane.py/moreton_bay.py. See constants.IDENTIFYING_USER_AGENT.

Structure: one accordion ("Agendas pre 2026") holds every agenda PDF as a
single flat list with no year sub-split; a second heading ("Past Minutes")
holds one accordion per year (2016-2025), each its own flat list of
minutes PDFs. Agenda and minutes lists are not paired in the DOM at all --
an agenda and its minutes live in entirely different accordions -- so
`scraper()` pairs them itself by (date, meeting type), parsed out of each
link's own title text.

A decade of hand-titled PDFs is not perfectly consistent, and this is a
real property of the source, not a scraper defect: dates separate with
"-", "_", or " " interchangeably (confirmed: "2022 03 23 Ordinary
Minutes" sits alongside "2022_03_09 Ordinary Minutes" in the very same
accordion) -- `_DOC_RE` accepts all three.

Not every PDF on the page is a meeting's own primary record. Skipped
entirely, as supplementary rather than a document in their own right:
appendices/attachments filed against a specific agenda item (e.g.
"2016_06_08 Attachment D", "2018_06_18 AppendixC_CapitalWorksProgram",
titles with no "Agenda"/"Minutes" suffix at all) and meeting *notices*
(e.g. "2025_07_01 Special Meeting Notice") -- a notice announces a
meeting rather than recording it, and the one found had a real Agenda and
Minutes for the same date anyway (confirmed directly, not assumed).
Same "ignore attachments, keep the primary record" rule moreton_bay.py
already uses.

Confirmed directly against the live site, not assumed to be a scraper
gap: the archive holds nothing newer than 2025-11-26, despite the page's
own content-warning footnote referencing an "8 July 2026 meeting" -- no
2026 agenda or minutes PDF is published anywhere on this domain. Checked
both /Your-Council/Minutes-and-Agendas and /Your-Council/Council-Meetings
(linked separately from the site nav) and they serve identical content,
not two different pages -- there is no separate "current agendas" page
this scraper is missing.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from aus_council_scrapers.base import BaseScraper, ScraperReturn, register_scraper
from aus_council_scrapers.constants import IDENTIFYING_USER_AGENT

_URL = "https://www.somerset.qld.gov.au/Your-Council/Minutes-and-Agendas"

_DOC_RE = re.compile(
    r"^(\d{4})[-_ ](\d{2})[-_ ](\d{2})[-_ ]*(.*?)[-_ ]*(Agenda|Minutes)\s*$",
    re.IGNORECASE,
)


def _normalize_type(meeting_type: str) -> str:
    """Fold a parsed meeting-type fragment down to one canonical form, used
    both to key meetings (so an agenda and its minutes merge into one
    ScraperReturn) and to build the display name.

    Real-world titling is inconsistent about whether "Meeting"/"Council
    Meeting" is already spelled out (e.g. an agenda titled "Special Budget
    Meeting Agenda" next to that same meeting's minutes titled just
    "Special Budget Minutes") -- confirmed directly (2023-06-21: exactly
    this pair) rather than assumed, and keying on the raw string left them
    unmerged, each with only one of agenda_url/minutes_url, while also
    producing a duplicate ScraperReturn once display names were cleaned up
    to strip the redundant "Meeting Meeting" this same inconsistency
    causes (e.g. "Special Council Meeting" naively became "Special Council
    Meeting Council Meeting"). Stripping "(council )meeting" before keying
    fixes both at once, and is safe to do at the keying level specifically
    because it only ever removes that one word/phrase -- it cannot merge
    two genuinely different meeting types (confirmed several dates hold
    two distinct real meetings, e.g. 2024-07-10 has both a real "Special
    Budget Meeting" and a real "Ordinary" meeting; "Special Budget" and
    "Ordinary" normalize to different strings regardless, so stay separate
    entries as they should).
    """
    core = re.sub(r"\b(council\s+)?meeting\b", "", meeting_type, flags=re.IGNORECASE)
    core = re.sub(r"[-_]+", " ", core)
    core = re.sub(r"\s+", " ", core).strip()
    return core.title() or "Ordinary"


def _parse_documents(soup: BeautifulSoup) -> dict[tuple[str, str], dict[str, str]]:
    """(date, normalized meeting type) -> {agenda_url, minutes_url}, merged
    across every accordion on the page regardless of which one a link
    lives in."""
    meetings: dict[tuple[str, str], dict[str, str]] = {}
    for link in soup.select("a.document"):
        title = (link.get("title") or link.get_text(" ", strip=True)).strip()
        m = _DOC_RE.match(title)
        if not m:
            continue  # attachment/appendix/notice -- not a primary record
        year, month, day, meeting_type, kind = m.groups()
        date = f"{year}-{month}-{day}"
        key = (date, _normalize_type(meeting_type))
        docs = meetings.setdefault(key, {})
        url_key = "agenda_url" if kind.lower() == "agenda" else "minutes_url"
        docs.setdefault(url_key, urljoin(_URL, link["href"]))
    return meetings


@register_scraper
class SomersetScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            "somerset",
            "QLD",
            "https://www.somerset.qld.gov.au",
            user_agent=IDENTIFYING_USER_AGENT,
        )

    def scraper(self) -> list[ScraperReturn]:
        html = self.fetcher.fetch_with_requests(_URL)
        soup = BeautifulSoup(html, "html.parser")

        meetings = _parse_documents(soup)
        results = [
            ScraperReturn(
                name=f"{meeting_type} Council Meeting",
                date=date,
                time=None,
                webpage_url=_URL,
                agenda_url=docs.get("agenda_url"),
                minutes_url=docs.get("minutes_url"),
                download_url=docs.get("agenda_url") or docs.get("minutes_url"),
                location=None,
            )
            for (date, meeting_type), docs in sorted(meetings.items())
        ]

        if not results:
            self.logger.warning("somerset found no meetings")
        else:
            self.logger.info(f"somerset scraper found {len(results)} meetings")
        return results
