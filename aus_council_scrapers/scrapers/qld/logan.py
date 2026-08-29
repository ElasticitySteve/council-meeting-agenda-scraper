"""Logan City Council publishes its meetings through eSCRIBE, a hosted
ASP.NET meeting platform, at pub-logancity.escribemeetings.com. This is a
new platform for this repo -- no base class -- but it needs no parser: its
public calendar is backed by a single JSON endpoint.

    POST /MeetingsCalendarView.aspx/GetCalendarMeetings
    Content-Type: application/json
    body: {"calendarStartDate": "YYYY-MM-DD", "calendarEndDate": "YYYY-MM-DD"}

One call covers the whole range in one response -- confirmed directly: a
2020-2027 call returns byte-for-byte the same meeting set as summing three
narrower ranges (475 meetings, 0 missed), so there is no pagination or
result cap to work around.

Logan's own site (logan.qld.gov.au) only links out to eSCRIBE and
separately 403s our default User-Agent (issue #142) -- but the eSCRIBE
subdomain does not, and this scraper never touches logan.qld.gov.au, so no
IDENTIFYING_USER_AGENT opt-in is needed here.

Each meeting carries a `MeetingDocumentLink` list. Only the entries titled
exactly "Agenda (PDF)", "Agenda (HTML)", "Minutes (PDF)" and
"Minutes (HTML)" are read: the "Agenda Cover Page", "Post Agenda",
"Revised Agenda", "Addendum" and "Confirmed Minutes" (Type
`AdditionalDocuments`) variants that sit alongside them are supplementary,
not the meeting's primary record -- the same "keep the primary record,
skip the attachments" rule moreton_bay.py and somerset.py already use.
PDF links resolve to /FileStream.ashx (confirmed: application/pdf);
HTML links to /Meeting.aspx.
"""

from __future__ import annotations

import json
import urllib.parse

from aus_council_scrapers import clock
from aus_council_scrapers.base import BaseScraper, ScraperReturn, register_scraper
from aus_council_scrapers.constants import EARLIEST_YEAR

_BASE = "https://pub-logancity.escribemeetings.com"
_CALENDAR_URL = f"{_BASE}/"
_ENDPOINT = f"{_BASE}/MeetingsCalendarView.aspx/GetCalendarMeetings"

# Document-link titles we keep, mapped to the ScraperReturn field they fill.
# Matched on the exact (lower-cased) title so "Post Agenda (PDF)", "Revised
# Agenda (PDF)", "Agenda Cover Page (PDF)" etc. fall through untouched.
_DOC_FIELD_BY_TITLE = {
    "agenda (pdf)": "agenda_url",
    "agenda (html)": "agenda_html_url",
    "minutes (pdf)": "minutes_url",
    "minutes (html)": "minutes_html_url",
}


@register_scraper
class LoganScraper(BaseScraper):
    def __init__(self):
        super().__init__("logan", "QLD", "https://www.logan.qld.gov.au")

    def scraper(self) -> list[ScraperReturn]:
        payload = {
            "calendarStartDate": f"{EARLIEST_YEAR}-01-01",
            "calendarEndDate": f"{clock.current_year() + 2}-12-31",
        }
        body = self.fetcher.fetch_with_requests(
            _ENDPOINT,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        meetings = json.loads(body).get("d") or []

        results: list[ScraperReturn] = []
        for meeting in meetings:
            docs: dict[str, str] = {}
            for link in meeting.get("MeetingDocumentLink") or []:
                field = _DOC_FIELD_BY_TITLE.get((link.get("Title") or "").strip().lower())
                if field and field not in docs and link.get("Url"):
                    docs[field] = urllib.parse.urljoin(_BASE, link["Url"])

            if "agenda_url" not in docs and "minutes_url" not in docs:
                continue

            # "2024/02/06 09:30:00" -> date "2024-02-06", time "09:30:00"
            date_part, _, time_part = (meeting.get("StartDate") or "").partition(" ")
            if not date_part:
                continue

            results.append(
                ScraperReturn(
                    name=meeting.get("MeetingName") or meeting.get("MeetingType"),
                    date=date_part.replace("/", "-"),
                    time=time_part or None,
                    webpage_url=_CALENDAR_URL,
                    agenda_url=docs.get("agenda_url"),
                    minutes_url=docs.get("minutes_url"),
                    agenda_html_url=docs.get("agenda_html_url"),
                    minutes_html_url=docs.get("minutes_html_url"),
                    download_url=docs.get("agenda_url") or docs.get("minutes_url"),
                    location=meeting.get("Location") or None,
                )
            )

        if not results:
            self.logger.warning("logan found no meetings")
        else:
            self.logger.info(f"logan scraper found {len(results)} meetings")
        return results
