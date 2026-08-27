"""Shared paging for QLD councils on OpenCities' "seamless pagination"
listing widget (see platforms.py's OpenCities signature), driven over plain
HTTP POST rather than Selenium.

The widget carries a page <select>, a "Go" submit button, and "Previous"/
"Next" submit buttons. "Next" looks like the natural control to click, but
POSTing it silently re-serves the *current* page -- confirmed directly
against both moreton_bay.py and gold_coast.py (fetched the same "next" page
twice and compared), not guessed. Setting the page <select> to the target
page number and submitting "Go" instead advances correctly -- but only if
Previous/Next are dropped from the POST body entirely: leaving them present
alongside Go (at their current, unclicked values) reproduces the same
stuck-on-one-page symptom, apparently because the postback picks Next as
the trigger whenever more than one submit button is present. Confirmed by
reproducing it (a first version of this module left them in) and fixing it
by dropping every submit button in the widget except the one actually being
clicked.

Each site names its own controls differently (Moreton Bay: ctl09$ctl00$...,
Gold Coast: ctl10$ctl00$...) -- the field names are read from the page
itself rather than hardcoded, so this works unchanged on either.
"""

from __future__ import annotations

from bs4 import BeautifulSoup


def form_fields(soup: BeautifulSoup) -> dict[str, str]:
    """Every named field in the page's form, at its current value -- the
    starting point for a postback, which must resubmit everything else
    unchanged."""
    form = soup.find("form")
    fields: dict[str, str] = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name")
        if not name:
            continue
        if inp.name == "select":
            opt = inp.find("option", selected=True) or inp.find("option")
            fields[name] = opt.get("value", "") if opt else ""
        else:
            fields[name] = inp.get("value", "")
    return fields


def total_pages(soup: BeautifulSoup) -> int:
    """1 if the page carries no pagination widget at all (a listing that
    fits on one page)."""
    pag = soup.find("div", class_="seamless-pagination")
    select = pag.find("select") if pag else None
    if not select:
        return 1
    options = select.find_all("option")
    return int(options[-1]["value"]) if options else 1


def next_page_fields(
    soup: BeautifulSoup, target_page: int, drop: tuple[str, ...] = ()
) -> dict[str, str] | None:
    """Form fields for requesting `target_page` of a seamless-pagination
    listing, or None if the widget isn't on this page. `drop` removes
    site-specific fields that shouldn't be resubmitted (a keyword search
    box, its own submit button) -- everything else carries over unchanged,
    as a postback expects."""
    pag = soup.find("div", class_="seamless-pagination")
    if pag is None:
        return None
    select = pag.find("select")
    go = pag.find("input", attrs={"title": "Change page"})
    if select is None or go is None:
        return None

    fields = form_fields(soup)
    for name in drop:
        fields.pop(name, None)
    # Drop every submit button in the pagination widget -- see module
    # docstring for why leaving Previous/Next present alongside Go breaks
    # the postback. Only the Go button being clicked should remain.
    for button in pag.find_all("input", attrs={"type": "submit"}):
        fields.pop(button.get("name"), None)

    fields[select["name"]] = str(target_page)
    fields[go["name"]] = go.get("value", "Go")
    return fields
