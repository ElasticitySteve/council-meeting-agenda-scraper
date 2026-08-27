from aus_council_scrapers.base import InfoCouncilScraper, register_scraper


@register_scraper
class ScenicRimScraper(InfoCouncilScraper):
    def __init__(self):
        council = "scenic_rim"
        state = "QLD"
        base_url = "https://www.scenicrim.qld.gov.au"
        infocouncil_url = "https://scenicrim.infocouncil.biz/"
        super().__init__(council, state, base_url, infocouncil_url)
