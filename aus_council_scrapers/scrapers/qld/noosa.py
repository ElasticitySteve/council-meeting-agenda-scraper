"""Noosa Council publishes its meetings through "Resolve" (a redsol /
CivicClerk product), a single-page app at noosa.resolve.red backed by a
JSON API at api.resolve.red. This is a new platform for this repo -- no
base class -- but the SPA shell is only 567 bytes and everything it shows
comes from the API, so there is no page to parse and no Selenium needed.

Noosa's own site (noosa.qld.gov.au) only embeds the portal in an iframe
and separately 403s our default User-Agent (issue #142); api.resolve.red
does not, and this scraper never touches noosa.qld.gov.au.

The API needs one header -- ``X-RESOLVE-CLIENT: noosa`` -- which the portal
derives from its own hostname. Meetings come from:

    GET /public/Events?type=past&page=N&startDate=&endDate=   (paginated)
    GET /public/Events?type=future&page=N                     (paginated)
    GET /public/Events?type=current&page=N                    (paginated)
    GET /public/Events/{id}                                    (one meeting)

``type=past`` over a wide date range already returns future-dated meetings
too, but ``future``/``current`` are fetched and merged by id anyway so a
newly-scheduled meeting cannot slip through a boundary. The list response
omits document references (``agendaFile``/``minutesFile`` are null there);
the per-event detail carries them, so this scraper makes one detail call
per meeting -- but only for events the list marks ``isAgendaPublished``:
the others have no documents and their /public/Events/{id} returns 404
(confirmed: every 404 is an unpublished event, e.g. an as-yet-agenda-less
future meeting or a ceremonial "Declaration of Office"). A 404 on an event
that *was* marked published is tolerated and skipped rather than aborting
the whole run.

Resolve keeps every document in private Azure blob storage, reachable only
through a ~15-minute signed URL minted per request by /public/AgendaFiles
-- there is no stable direct PDF link to record. The stored links are
therefore the portal's own permalinks:

    agenda   -> noosa.resolve.red/portal/meeting/{id}?agendaFile=1
    minutes  -> noosa.resolve.red/portal/meeting/{id}?agendaFile=3
    HTML agenda view (webpage_url) -> noosa.resolve.red/portal/meeting/{id}

Coverage: the Resolve portal only goes back to April 2023 (confirmed: the
oldest event is 2023-04-11). Noosa's pre-2023 agenda archive is a separate
page on noosa.qld.gov.au, behind the #142 User-Agent block, so it is out
of reach until that is resolved -- the same deferral the archive would hit
directly, not a defect in this scraper.
"""

from __future__ import annotations

import json

import requests

from aus_council_scrapers import clock
from aus_council_scrapers.base import BaseScraper, ScraperReturn, register_scraper
from aus_council_scrapers.constants import EARLIEST_YEAR

_API = "https://api.resolve.red"
_PORTAL = "https://noosa.resolve.red/portal"
_HEADERS = {"X-RESOLVE-CLIENT": "noosa"}


@register_scraper
class NoosaScraper(BaseScraper):
    def __init__(self):
        super().__init__("noosa", "QLD", "https://www.noosa.qld.gov.au")

    def _get(self, path: str) -> dict:
        return json.loads(self.fetcher.fetch_with_requests(_API + path, headers=_HEADERS))

    def _list(self, query: str) -> list[dict]:
        """Every page of one /public/Events listing."""
        first = self._get(f"/public/Events?{query}&page=1")
        events = list(first.get("results") or [])
        for page in range(2, (first.get("totalPages") or 1) + 1):
            events.extend(self._get(f"/public/Events?{query}&page={page}").get("results") or [])
        return events

    def scraper(self) -> list[ScraperReturn]:
        date_range = (
            f"startDate={EARLIEST_YEAR}-01-01"
            f"&endDate={clock.current_year() + 2}-12-31"
        )

        by_id: dict[int, dict] = {}
        for query in (f"type=past&{date_range}", "type=future", "type=current"):
            for event in self._list(query):
                by_id.setdefault(event["id"], event)

        results: list[ScraperReturn] = []
        for event_id, listing in sorted(by_id.items()):
            if not listing.get("isAgendaPublished"):
                # No published agenda -> no documents, and /public/Events/{id}
                # 404s for these. Nothing to emit.
                continue
            try:
                detail = self._get(f"/public/Events/{event_id}")
            except requests.HTTPError as exc:
                self.logger.warning(f"noosa: skipping event {event_id} ({exc})")
                continue

            agenda_url = (
                f"{_PORTAL}/meeting/{event_id}?agendaFile=1"
                if detail.get("agendaFile")
                else None
            )
            minutes_url = (
                f"{_PORTAL}/meeting/{event_id}?agendaFile=3"
                if detail.get("minutesFile")
                else None
            )
            if not agenda_url and not minutes_url:
                continue

            # "2023-06-06T09:30:00" -> date "2023-06-06", time "09:30:00"
            event_date, _, event_time = (detail.get("eventDate") or "").partition("T")
            if not event_date:
                continue

            results.append(
                ScraperReturn(
                    name=detail.get("meetingTypeName") or detail.get("name"),
                    date=event_date,
                    time=event_time or None,
                    webpage_url=f"{_PORTAL}/meeting/{event_id}",
                    agenda_url=agenda_url,
                    minutes_url=minutes_url,
                    download_url=agenda_url or minutes_url,
                    location=detail.get("eventLocation") or None,
                )
            )

        if not results:
            self.logger.warning("noosa found no meetings")
        else:
            self.logger.info(f"noosa scraper found {len(results)} meetings")
        return results
