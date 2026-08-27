from aus_council_scrapers.base import InfoCouncilScraper, register_scraper


@register_scraper
class SunshineCoastScraper(InfoCouncilScraper):
    def __init__(self):
        council = "sunshine_coast"
        state = "QLD"
        base_url = "https://www.sunshinecoast.qld.gov.au"
        infocouncil_url = "https://sunshinecoast.infocouncil.biz/"
        super().__init__(council, state, base_url, infocouncil_url)
