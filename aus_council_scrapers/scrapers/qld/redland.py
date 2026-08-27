from aus_council_scrapers.base import InfoCouncilScraper, register_scraper


@register_scraper
class RedlandScraper(InfoCouncilScraper):
    def __init__(self):
        council = "redland_qld"
        state = "QLD"
        base_url = "https://www.redland.qld.gov.au"
        infocouncil_url = "https://redland.infocouncil.biz/"
        super().__init__(council, state, base_url, infocouncil_url)
