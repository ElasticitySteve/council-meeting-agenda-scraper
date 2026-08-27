from aus_council_scrapers.base import InfoCouncilScraper, register_scraper


@register_scraper
class IpswichScraper(InfoCouncilScraper):
    def __init__(self):
        council = "ipswich"
        state = "QLD"
        base_url = "https://www.ipswich.qld.gov.au"
        infocouncil_url = "https://ipswich.infocouncil.biz/"
        super().__init__(council, state, base_url, infocouncil_url)
