from tfmkt.spiders.common import BaseSpider
from urllib.parse import unquote, urlparse
import re

class ClubsSpider(BaseSpider):
    name = 'clubs'

    def parse(self, response, parent):
        """
        Parse the competition page. Transfermarkt pages may contain more than one
        "responsive-table" block for teams (for example, one for first tier and another for second tier).
        We iterate over all tables that appear to have team data.
        
        @url https://www.transfermarkt.co.uk/premier-league/startseite/wettbewerb/GB1
        @returns requests
        @cb_kwargs {"parent": "dummy"}
        @scrapes type href parent
        """
        def is_teams_table(table):
            # Get all header texts from the table.
            headers = [h.strip().lower() for h in table.css('th::text').getall() if h]
            # We consider it a teams table if any header contains "club"
            return any("club" in hdr for hdr in headers)

        def extract_team_href(row):
            # Expect that the second <td> contains the club link.
            tds = row.css('td')
            if len(tds) >= 2:
                return tds[1].css('a::attr(href)').get()
            return None

        page_tables = response.css('div.responsive-table')
        teams_tables = [table for table in page_tables if is_teams_table(table)]
        self.logger.info("Found %d responsive-table(s) on %s", len(teams_tables), response.url)

        # Instead of asserting exactly one table, iterate over all found tables.
        for table in teams_tables:
            for row in table.css('tbody tr'):
                href = extract_team_href(row)
                if not href:
                    continue
                # Remove any trailing season info (e.g. '/saison_id/2024')
                href_strip_season = re.sub(r'/saison_id/\d{4}$', '', href)
                cb_kwargs = {
                    'base': {
                        'type': 'club',
                        'href': href_strip_season,
                        'parent': parent  # parent comes from the competition item
                    }
                }
                yield response.follow(href, self.parse_details, cb_kwargs=cb_kwargs)

    def parse_details(self, response, base):
        """
        Extract club details from the club page.
        
        @url https://www.transfermarkt.co.uk/fc-bayern-munchen/startseite/verein/27
        @returns items 1 1
        @cb_kwargs {"base": {"href": "some_href/path/to/code", "type": "club", "parent": {}}}
        @scrapes href type parent
        """
        attributes = {}

        # Extract market value from the "dataMarktwert" section
        attributes['total_market_value'] = response.css('div.dataMarktwert a::text').get()

        # Extract squad size and average age from the "dataContent" section
        attributes['squad_size'] = self.safe_strip(response.xpath("//li[contains(text(),'Squad size:')]/span/text()").get())
        attributes['average_age'] = self.safe_strip(response.xpath("//li[contains(text(),'Average age:')]/span/text()").get())

        # Extract foreigners information
        foreigners_li = response.xpath("//li[contains(text(),'Foreigners:')]")
        if foreigners_li:
            attributes['foreigners_number'] = self.safe_strip(foreigners_li[0].xpath("span/a/text()").get())
            attributes['foreigners_percentage'] = self.safe_strip(foreigners_li[0].xpath("span/span/text()").get())
        else:
            attributes['foreigners_number'] = None
            attributes['foreigners_percentage'] = None

        # Extract national team players
        attributes['national_team_players'] = self.safe_strip(response.xpath("//li[contains(text(),'National team players:')]/span/a/text()").get())

        # Extract stadium details
        stadium_li = response.xpath("//li[contains(text(),'Stadium:')]")
        if stadium_li:
            attributes['stadium_name'] = self.safe_strip(stadium_li[0].xpath("span/a/text()").get())
            attributes['stadium_seats'] = self.safe_strip(stadium_li[0].xpath("span/span/text()").get())
        else:
            attributes['stadium_name'] = None
            attributes['stadium_seats'] = None

        # Extract net transfer record and coach name
        attributes['net_transfer_record'] = self.safe_strip(response.xpath("//li[contains(text(),'Current transfer record:')]/span/span/a/text()").get())
        coach_name = response.xpath('//div[contains(@data-viewport, "Mitarbeiter")]//div[@class="container-hauptinfo"]/a/text()').get()
        attributes['coach_name'] = coach_name.strip() if coach_name else None

        # Extract a short code from the club URL and the club name
        attributes['code'] = unquote(urlparse(base["href"]).path.split("/")[1])
        name_val = response.xpath("//span[@itemprop='legalName']/text()").get() or response.xpath('//h1[contains(@class,"data-header__headline-wrapper")]/text()').get()
        attributes['name'] = self.safe_strip(name_val)

        for key, value in attributes.items():
            if isinstance(value, str):
                attributes[key] = value.strip()

        yield {**base, **attributes}
