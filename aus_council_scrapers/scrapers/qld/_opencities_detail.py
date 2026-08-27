"""Shared meeting-detail parsing for QLD councils on OpenCities' meeting
template (see platforms.py's OpenCities signature): a field-label/field-value
list (Meeting date/type), a `div.meeting-time`, a `div.meeting-address`, and
one or more `div.meeting-document` blocks (a heading plus PDF link(s)).
Confirmed identical across moreton_bay.py and gold_coast.py right down to
the CSS class names -- only the field-label capitalisation ("Meeting date"
vs "Meeting Date") and each council's own document-heading wording differ,
so `field_value` matches case-insensitively and heading classification
stays with each scraper (via `classify_documents`'s `ignore` pattern).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def field_value(soup: BeautifulSoup, label_text: str) -> str | None:
    target = label_text.lower()
    for li in soup.find_all("li"):
        label = li.find("span", class_="field-label")
        if label and label.get_text(strip=True).lower() == target:
            value = li.find("span", class_="field-value")
            return value.get_text(" ", strip=True) if value else None
    return None


def extract_time(soup: BeautifulSoup) -> str | None:
    div = soup.find("div", class_="meeting-time")
    if not div:
        return None
    texts = [t.strip() for t in div.find_all(string=True, recursive=False) if t.strip()]
    return texts[0] if texts else None


def extract_location(soup: BeautifulSoup) -> str | None:
    div = soup.find("div", class_="meeting-address")
    p = div.find("p") if div else None
    if not p:
        return None
    texts = [t.strip() for t in p.find_all(string=True, recursive=False) if t.strip()]
    return texts[0] if texts else None


def document_blocks(soup: BeautifulSoup, page_url: str) -> list[tuple[str, list[str]]]:
    """(heading text, [absolute urls]) for every `div.meeting-document` on
    the page, in document order. A heading with no link at all (an agenda
    item like "9.00am Declaration of Office Ceremony" rather than an actual
    document) comes back with an empty list.

    An older template (seen on Gold Coast meetings from ~2020-2021) has no
    `<h2>` at all -- the same text sits in a sibling
    `div.meeting-document-title span` instead (e.g. "Special B&F Committee
    Meeting 26 November 2020 agenda"). Confirmed directly, not guessed:
    both forms are read the same way so classification and any
    heading-derived fallback (see gold_coast.py) work on either.
    """
    blocks = []
    for div in soup.find_all("div", class_="meeting-document"):
        h2 = div.find("h2")
        if h2:
            heading = h2.get_text(strip=True)
        else:
            title = div.find("div", class_="meeting-document-title")
            heading = title.get_text(strip=True) if title else ""
        links = [urljoin(page_url, a["href"]) for a in div.find_all("a", href=True)]
        blocks.append((heading, links))
    return blocks


def classify_documents(
    soup: BeautifulSoup, page_url: str, ignore: re.Pattern | None = None
) -> dict[str, str]:
    """First agenda_url/minutes_url found among a page's document blocks.

    A heading containing "agenda" or "minutes" is classified accordingly;
    `ignore` lets a council mark its own attachment-style headings (Moreton
    Bay's "...supporting information", "...tabled/presented at the
    meeting") to skip; anything else -- typically a committee that
    publishes one combined, non-split document -- is treated as the agenda,
    since it's the meeting's one substantive record.
    """
    docs: dict[str, str] = {}
    for heading, links in document_blocks(soup, page_url):
        if not links:
            continue
        low = heading.lower()
        if "minutes" in low:
            docs.setdefault("minutes_url", links[0])
        elif "agenda" in low:
            docs.setdefault("agenda_url", links[0])
        elif ignore and ignore.search(low):
            continue
        else:
            docs.setdefault("agenda_url", links[0])
    return docs
