"""Gold Coast publishes every meeting (Council and its committees) as its
own detail page under /Council/Council-meetings/Minutes-agendas/<slug>,
indexed by a paginated OpenCities listing at
/Council/Council-meetings/Minutes-agendas -- the same widget as
moreton_bay.py (see platforms.py's OpenCities signature and
_opencities_paging.py), just a different council on it.

Gold Coast's own domain does NOT block DefaultFetcher's spoofed browser
User-Agent -- confirmed directly, unlike moreton_bay.py/brisbane.py, so no
`user_agent` override is set here.

Detail pages use `_opencities_detail`, shared with moreton_bay.py. Two
things are Gold Coast-specific:

  - Slugs only carry a date for recent meetings (e.g.
    ".../25-August-2026-Council"); meetings from ~2021 and earlier are
    referenced by an opaque "Round-<n>-<id>" slug with no date in the URL
    at all -- confirmed directly, not a scraper bug. The accordion's own
    listing text always carries a leading date regardless, so that (not
    the href) is what `_iter_stub_urls` reads to know when to stop
    paginating past _MIN_YEAR.

  - Meetings from that same ~2020-2021 period also have a blank
    "Meeting Type" field (the listing shows just a date, e.g. "26 November
    2020", with no committee suffix) -- confirmed directly against the raw
    page, not a parsing artifact. Their one document's own heading still
    names the meeting, e.g. "Special B&F Committee Meeting 26 November
    2020 agenda", so `_name_from_heading` recovers it from there instead.
    Moot at the current _MIN_YEAR cutoff (both are pre-2022), kept because
    it's cheap and the cutoff may not stay put.

_MIN_YEAR is 2022, not constants.EARLIEST_YEAR (2020) -- a deliberate,
Gold-Coast-specific scope decision (Gold Coast has ~600 meetings back to
2020; going back only to 2022 was judged enough, full history "just
ancient history"), not a change to the project-wide floor other scrapers
are still held to.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from aus_council_scrapers.base import BaseScraper, ScraperReturn, register_scraper
from aus_council_scrapers.scrapers.qld import _opencities_detail as detail
from aus_council_scrapers.scrapers.qld import _opencities_paging as paging

_INDEX_URL = "https://www.goldcoast.qld.gov.au/Council/Council-meetings/Minutes-agendas"

_MIN_YEAR = 2022

# The keyword-search box and its own submit button (twice over -- there are
# two search widgets on this page, as on moreton_bay.py) -- not part of
# paging, but present in the same <form> and must not be resubmitted as if
# clicked.
_DROP_FIELDS = ("ctl07$txtSearch", "ctl07$btnSearch", "ctl10$ctl00$ctl19")

_MONTH = (
    r"January|February|March|April|May|June|July|August"
    r"|September|October|November|December"
)
_LEADING_DATE = re.compile(rf"^(\d{{1,2}}\s+(?:{_MONTH})\s+(\d{{4}}))\b", re.IGNORECASE)
_HEADING_DATE = re.compile(rf"^(.*?)\s+\d{{1,2}}\s+(?:{_MONTH})\s+\d{{4}}\b", re.IGNORECASE)


def _stub_items(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """(href, listing text) for every meeting on the current page."""
    items = []
    for item in soup.select(".accordion-list-item-container"):
        a = item.find("a", href=True)
        if a:
            items.append((a["href"], item.get_text(" ", strip=True)))
    return items


def _listing_year(text: str) -> int | None:
    m = _LEADING_DATE.match(text)
    return int(m.group(2)) if m else None


def _name_from_heading(soup: BeautifulSoup, page_url: str) -> str | None:
    for heading, links in detail.document_blocks(soup, page_url):
        if not links:
            continue
        m = _HEADING_DATE.match(heading.strip())
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


@register_scraper
class GoldCoastScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            "gold_coast", "QLD", "https://www.goldcoast.qld.gov.au"
        )

    def _iter_stub_urls(self):
        html = self.fetcher.fetch_with_requests(_INDEX_URL)
        soup = BeautifulSoup(html, "html.parser")
        page = 1
        while True:
            for href, text in _stub_items(soup):
                year = _listing_year(text)
                if year is not None and year < _MIN_YEAR:
                    return
                yield href

            if page >= paging.total_pages(soup):
                return

            page += 1
            fields = paging.next_page_fields(soup, page, drop=_DROP_FIELDS)
            if fields is None:
                return
            html = self.fetcher.fetch_with_requests(_INDEX_URL, method="POST", data=fields)
            soup = BeautifulSoup(html, "html.parser")

    def _parse_detail(self, url: str, html: str) -> ScraperReturn | None:
        soup = BeautifulSoup(html, "html.parser")
        date = detail.field_value(soup, "Meeting Date")
        name = detail.field_value(soup, "Meeting Type") or _name_from_heading(soup, url)
        if not date or not name:
            self.logger.warning(f"gold_coast: no Meeting Date/Type recoverable for {url}")
            return None

        docs = detail.classify_documents(soup, url)
        if not docs:
            return None

        return ScraperReturn(
            name=name,
            date=date,
            time=detail.extract_time(soup),
            webpage_url=url,
            agenda_url=docs.get("agenda_url"),
            minutes_url=docs.get("minutes_url"),
            download_url=docs.get("agenda_url") or docs.get("minutes_url"),
            location=detail.extract_location(soup),
        )

    def scraper(self) -> list[ScraperReturn]:
        results = []
        for href in self._iter_stub_urls():
            html = self.fetcher.fetch_with_requests(href)
            record = self._parse_detail(href, html)
            if record:
                results.append(record)

        if not results:
            self.logger.warning("gold_coast found no meetings")
        else:
            self.logger.info(f"gold_coast scraper found {len(results)} meetings")
        return results
