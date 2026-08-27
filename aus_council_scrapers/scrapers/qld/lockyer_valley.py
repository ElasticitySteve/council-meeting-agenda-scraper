from aus_council_scrapers.base import InfoCouncilScraper, register_scraper


@register_scraper
class LockyerValleyScraper(InfoCouncilScraper):
    def __init__(self):
        council = "lockyer_valley"
        state = "QLD"
        base_url = "https://www.lockyervalley.qld.gov.au"
        infocouncil_url = "https://lockyervalley.infocouncil.biz/"
        super().__init__(council, state, base_url, infocouncil_url)
