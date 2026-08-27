"""Moreton Bay publishes every meeting (Council and its committees) as its
own detail page under /Council/Meetings/<year>/<slug>, indexed by a
paginated OpenCities listing at /Council/Meetings -- no known platform (see
platforms.py), just this council's own OpenCities "Minutes and Agenda"
module.

Moreton Bay's own domain blocks DefaultFetcher's spoofed browser User-Agent
(403) but returns 200 for an honest, identifying one -- confirmed directly
against this domain, the same way as brisbane.py. See
constants.IDENTIFYING_USER_AGENT.

Pagination is handled by `_opencities_paging` (see that module for the
"Next" quirk it works around) -- shared with gold_coast.py, the other QLD
council on this same listing widget. Pagination stops once a page's
meetings fall below EARLIEST_YEAR (the list is newest-first), matching the
bound convention other scrapers use for EARLIEST_YEAR (see constants.py).

Each meeting's own page carries "Meeting date"/"Meeting type" fields (used
for `date`/`name`) and one or more `.meeting-document` blocks, each a
heading + PDF link(s):

  - a heading containing "agenda" -> agenda_url (first link)
  - a heading containing "minutes" -> minutes_url (first link)
  - "...supporting information" / "...documents (as tabled/presented at the
    meeting)" -- attachments and tabled papers, not a meeting record on
    their own -- ignored
  - anything else (e.g. "Audit report and recommendations", a committee
    that never splits agenda from minutes) -- treated as the agenda, since
    it's the meeting's one substantive document
  - a heading with no link at all (e.g. "9.00am Declaration of Office
    Ceremony", an agenda item rather than a document) -- ignored

Confirmed directly against the live site, not assumed to be a scraper
defect: as of this scraper being written, the public listing's newest entry
is 07 November 2024 -- nothing more recent has been published there despite
a 2025-26 meeting schedule PDF existing elsewhere on the site. That gap is
in Moreton Bay's own published index, not something to route around here.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from aus_council_scrapers.base import BaseScraper, ScraperReturn, register_scraper
from aus_council_scrapers.constants import EARLIEST_YEAR, IDENTIFYING_USER_AGENT
from aus_council_scrapers.scrapers.qld import _opencities_detail as detail
from aus_council_scrapers.scrapers.qld import _opencities_paging as paging

_INDEX_URL = "https://www.moretonbay.qld.gov.au/Council/Meetings"

_HREF_YEAR = re.compile(r"/Council/Meetings/(\d{4})/")

# The keyword-search box and its own submit button -- not part of paging,
# but present in the same <form> and must not be resubmitted as if clicked.
_DROP_FIELDS = ("ctl06$txtSearch", "ctl06$btnSearch", "ctl09$ctl00$ctl19")

# Attachments and tabled papers, not a meeting record on their own -- see
# _opencities_detail.classify_documents.
_IGNORED_DOCUMENT_HEADINGS = re.compile(
    r"supporting information|tabled|presented at the meeting", re.IGNORECASE
)


def _stub_hrefs(soup: BeautifulSoup) -> list[str]:
    hrefs = []
    for item in soup.select(".accordion-list-item-container"):
        a = item.find("a", href=True)
        if a:
            hrefs.append(a["href"])
    return hrefs


def _href_year(href: str) -> int | None:
    m = _HREF_YEAR.search(href)
    return int(m.group(1)) if m else None


@register_scraper
class MoretonBayScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            "moreton_bay",
            "QLD",
            "https://www.moretonbay.qld.gov.au",
            user_agent=IDENTIFYING_USER_AGENT,
        )

    def _iter_stub_urls(self):
        html = self.fetcher.fetch_with_requests(_INDEX_URL)
        soup = BeautifulSoup(html, "html.parser")
        page = 1
        while True:
            for href in _stub_hrefs(soup):
                year = _href_year(href)
                if year is not None and year < EARLIEST_YEAR:
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
        date = detail.field_value(soup, "Meeting date")
        name = detail.field_value(soup, "Meeting type")
        if not date or not name:
            self.logger.warning(f"moreton_bay: no Meeting date/type field on {url}")
            return None

        docs = detail.classify_documents(soup, url, ignore=_IGNORED_DOCUMENT_HEADINGS)
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
            self.logger.warning("moreton_bay found no meetings")
        else:
            self.logger.info(f"moreton_bay scraper found {len(results)} meetings")
        return results
