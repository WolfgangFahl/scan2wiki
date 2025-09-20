"""
Created on 2023-11-16

@author: wf
"""

import random
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from scan.product import Product


class Amazon:
    """
    lookup products on amazon web site
    """

    def __init__(self, debug: Optional[bool] = False):
        """
        constructor

        Args:
            debug (bool, optional): If set to True, pretty-prints the first product div for debugging.
        """
        self.debug = debug

    def extract_amazon_products(self, soup: BeautifulSoup) -> List[Product]:
        """
        Parse an Amazon search result page (soup) into a list of Product objects.

        Amazon’s HTML changes often. As of now, each product is wrapped in:
          <div data-component-type="s-search-result"> ... </div>

        Inside each result we extract:
          - title: from h2 > a
          - image_url: from <img class="s-image">
          - asin: from any link containing "/dp/<ASIN>"
          - price: from <span class="a-price"><span class="a-offscreen">...</span></span>
        """
        products: List[Product] = []

        # Find all result containers
        items = soup.find_all("div", attrs={"data-component-type": "s-search-result"})

        # If debug mode is on, pretty-print the first result for inspection
        if self.debug and items:
            print("Debug - First Result Item:")
            print(items[0].prettify())

        # Iterate over each search result
        for item in items:
            title = ""
            image_url = ""
            asin = ""
            price = ""

            # Extract product title
            link = item.select_one("a h2")
            if link:
                title = link.get_text(strip=True)

            # Extract product image
            img = item.select_one("img.s-image")
            if img and img.get("src"):
                image_url = img["src"]

            # Extract ASIN from product link
            asin_link = item.select_one('a[href*="/dp/"]')
            if asin_link and asin_link.get("href"):
                href = asin_link["href"]
                if "/dp/" in href:
                    asin = href.split("/dp/")[-1].split("/")[0]

            # Extract product price
            offscreen = item.select_one("span.a-price > span.a-offscreen")
            if offscreen:
                # Normalize non-breaking spaces in prices
                price = offscreen.get_text(strip=True).replace("\xa0", " ")

            # Only create a Product if we at least found a title
            if title:
                products.append(Product(title=title, image_url=image_url, price=price, asin=asin))

        return products

    def visit_product(self, product: Product):
        """
        get product details from product page
        """
        if product.asin:
            soup = self.get_soup(product.amazon_url)
        # Example
        # Produktinformation
        # Herausgeber ‏ : ‎ Wiley
        # Erscheinungstermin ‏ : ‎ 26. Januar 2021
        # Auflage ‏ : ‎ 3.
        # Sprache ‏ : ‎ Englisch
        # Seitenzahl der Print-Ausgabe ‏ : ‎ 1232 Seiten
        # ISBN-10 ‏ : ‎ 1119642787
        # ISBN-13 ‏ : ‎ 978-1119642787
        # Abmessungen ‏ : ‎ 19.81 x 4.32 x 23.62 cm

        details = {}

        # Find product information section
        detail_section = soup.find("div", id="detailBullets_feature_div")
        if detail_section:
            if self.debug:
                print(product.amazon_url)
                print(detail_section.prettify())
            # Get all list items containing product details
            list_items = detail_section.find_all("li")

            # Extract label-value pairs from each list item
            for item in list_items:
                spans = item.find_all("span")
                if len(spans) >= 2:
                    # First span contains the label, last span contains the value
                    # Clean the label: remove Unicode marks, newlines, and split on colon
                    label_raw = spans[0].get_text(strip=True)
                    label = label_raw.split(':')[0].replace('\u200f', '').replace('\u200e', '').strip()
                    value = spans[-1].get_text(strip=True)
                    details[label] = value
            product.details=details
            pass

    def get_headers(self):
        # Possible components of a user agent string
        browsers = ["Chrome", "Firefox", "Safari", "Edge"]
        operating_systems = [
            "Windows NT 10.0; Win64; x64",
            "Macintosh; Intel Mac OS X 10_15_7",
            "X11; Linux x86_64",
        ]
        platforms = [
            "AppleWebKit/537.36 (KHTML, like Gecko)",
            "Gecko/20100101 Firefox/76.0",
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1 Safari/605.1.15",
        ]

        # Randomly select one component from each category
        browser = random.choice(browsers)
        os = random.choice(operating_systems)
        platform = random.choice(platforms)

        # Construct the user agent string
        user_agent = f"Mozilla/5.0 ({os}) {platform} {browser}/58.0.3029.110"

        headers = {"User-Agent": user_agent}
        return headers

    def get_soup(self, url: str) -> BeautifulSoup:
        """
        Get parsed HTML soup from URL.
        """
        headers = self.get_headers()
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Request to {url} failed with status {response.status_code}")

        soup= BeautifulSoup(response.content, "html.parser")
        return soup

    def lookup_products(self, search_key: str):
        """
        lookup the given search key e.g. ISBN or EAN
        """
        url = f"https://www.amazon.de/s?k={search_key}"
        soup = self.get_soup(url)

        product_list = self.extract_amazon_products(soup)
        if len(product_list)>0:
            self.visit_product(product_list[0])
        return product_list
