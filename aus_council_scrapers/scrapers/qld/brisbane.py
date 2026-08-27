"""Brisbane publishes every standing committee's and Council's own agendas
and minutes on a single page, 2020-present, with no year-based pagination
and no known platform (see platforms.py) -- one big page instead of a table.

Brisbane's own domain blocks DefaultFetcher's spoofed browser User-Agent
(403) but returns 200 for an honest, identifying one -- confirmed directly,
not assumed from the general #142 pattern (spoofed UA -> 403; honest UA,
with or without the rest of DEFAULTHEADERS -> 200 either way; no WAF-vendor
response headers present). See constants.IDENTIFYING_USER_AGENT.

The page has three data sections, each laid out differently:

  "Upcoming committee and Council meetings"
      One accordion per upcoming date ("Standing committee meetings -- 25
      August 2026", "Ordinary Council meeting -- 25 August 2026"), each
      holding one [Committee, Documents] table. A committee row's Documents
      list can mix this meeting's Agenda with a *different, earlier*
      meeting's "Minutes (unconfirmed) for <date>" -- deliberately not
      captured here: it duplicates whatever full/confirmed record files as
      an ordinary <date> minutes entry once it lands in the Past sections
      below, and would otherwise register as the same meeting emitted twice
      under two different provenances. Only the Agenda is read from this
      section; the accordion's own trailing date is the meeting date.

  "Past Council meeting minutes"
      One accordion per year, each a single [Meeting date, Minutes] table.
      Committee is always "Council".

  "Past standing committee meeting minutes and presentations"
      One accordion per committee (9 of them), each containing several
      separate blocks -- one per year -- of an <h4>YYYY minutes</h4>
      immediately followed by its own [Meeting date, Minutes, Presentations]
      table in the *same* container. Presentations are not part of
      ScraperReturn and are not read.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from aus_council_scrapers.base import BaseScraper, ScraperReturn, register_scraper
from aus_council_scrapers.constants import IDENTIFYING_USER_AGENT

_TRAILING_DATE = re.compile(
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)\s+\d{4})",
    re.IGNORECASE,
)


def _documents(cell) -> dict[str, str]:
    """First agenda_url and first minutes_url found in a Documents cell.
    Anything else (a committee "Report" tabled at a Council meeting, a
    Presentation) is not a meeting document and is ignored."""
    found: dict[str, str] = {}
    for link in cell.find_all("a", href=True):
        label = link.get_text(" ", strip=True).lower()
        if "agenda" in label and "agenda_url" not in found:
            found["agenda_url"] = link["href"]
        elif "minutes" in label and "unconfirmed" not in label and "minutes_url" not in found:
            found["minutes_url"] = link["href"]
    return found


def _cell_text(cell) -> str:
    return cell.get_text(" ", strip=True)


# Confirmed literal source typo (a "Meeting date" cell reads "20 Mary 2025" --
# checked directly against the raw page, not a parsing artifact). Narrow and
# explicit rather than fuzzy-correcting any date, matching how waverley.py
# handles its own confirmed day-first date quirk.
_KNOWN_DATE_TYPOS = {"mary": "may"}


def _fix_known_date_typos(date: str) -> str:
    words = date.split(" ")
    return " ".join(_KNOWN_DATE_TYPOS.get(w.lower(), w) for w in words)


def _make_return(name: str, date: str, webpage_url: str, docs: dict[str, str]) -> ScraperReturn | None:
    if not docs:
        return None
    return ScraperReturn(
        name=name,
        date=_fix_known_date_typos(date),
        time=None,
        webpage_url=webpage_url,
        agenda_url=docs.get("agenda_url"),
        minutes_url=docs.get("minutes_url"),
        download_url=docs.get("agenda_url") or docs.get("minutes_url"),
        location=None,
    )


def _section_headings(all_h3: list, start_text: str, end_text: str | None) -> list:
    """h3 tags strictly between one heading's text and the next, by document
    position -- several unrelated things on this page share a heading level,
    so slicing by an explicit start/end pair is the only reliable bound."""
    texts = [h.get_text(strip=True) for h in all_h3]
    start = texts.index(start_text) + 1
    end = texts.index(end_text) if end_text else len(all_h3)
    return all_h3[start:end]


@register_scraper
class BrisbaneScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            "brisbane",
            "QLD",
            "https://www.brisbane.qld.gov.au",
            user_agent=IDENTIFYING_USER_AGENT,
        )
        self._url = (
            "https://www.brisbane.qld.gov.au/about-council/governance-and-strategy/"
            "council-and-standing-committee-meetings"
        )

    def _parse_upcoming(self, soup: BeautifulSoup, all_h3: list) -> list[ScraperReturn]:
        results = []
        for h3 in _section_headings(all_h3, "Upcoming committee and Council meetings", "Past Council meeting minutes"):
            title = h3.get_text(strip=True)
            date_match = _TRAILING_DATE.search(title)
            if not date_match:
                continue
            date = date_match.group(1)
            table = h3.parent.find("table")
            if not table:
                continue
            for row in table.find_all("tr")[1:]:  # skip header row
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                committee = "Council" if "council meeting" in _cell_text(cells[0]).lower() else _cell_text(cells[0])
                docs = _documents(cells[1])
                docs.pop("minutes_url", None)  # see module docstring: agenda only, here
                record = _make_return(committee, date, self._url, docs)
                if record:
                    results.append(record)
        return results

    def _parse_past_council(self, soup: BeautifulSoup, all_h3: list) -> list[ScraperReturn]:
        results = []
        for h3 in _section_headings(
            all_h3, "Past Council meeting minutes", "Past standing committee meeting minutes and presentations"
        ):
            table = h3.parent.find("table")
            if not table:
                continue
            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                date = _cell_text(cells[0])
                docs = _documents(cells[1])
                record = _make_return("Council", date, self._url, docs)
                if record:
                    results.append(record)
        return results

    def _parse_past_committees(self, soup: BeautifulSoup, all_h3: list) -> list[ScraperReturn]:
        results = []
        for h3 in _section_headings(
            all_h3, "Past standing committee meeting minutes and presentations", "Publication scheme"
        ):
            committee = re.sub(r"\s+minutes$", "", h3.get_text(strip=True), flags=re.IGNORECASE)
            panel = h3.parent
            # Most committees break their history into one <h4>YYYY
            # minutes</h4> + <table> pair per year; a lightly-used committee
            # (Councillor Ethics) has just one table with no year heading at
            # all. The meeting date always comes from the table's own
            # "Meeting date" column regardless, so the h4 was never actually
            # needed for data -- only for locating the table -- and every
            # table in the panel can be read directly.
            for table in panel.find_all("table"):
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue
                    date = _cell_text(cells[0])
                    docs = _documents(cells[1])
                    record = _make_return(committee, date, self._url, docs)
                    if record:
                        results.append(record)
        return results

    def scraper(self) -> list[ScraperReturn]:
        html = self.fetcher.fetch_with_requests(self._url)
        soup = BeautifulSoup(html, "html.parser")
        all_h3 = soup.find_all("h3")

        results = (
            self._parse_upcoming(soup, all_h3)
            + self._parse_past_council(soup, all_h3)
            + self._parse_past_committees(soup, all_h3)
        )

        if not results:
            self.logger.warning("brisbane found no meetings")
        else:
            self.logger.info(f"brisbane scraper found {len(results)} meetings")
        return results
