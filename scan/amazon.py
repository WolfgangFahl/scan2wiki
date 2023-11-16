"""
Created on 12023-11-16

@author: wf
"""
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Product:
    """
    Data class representing a product.

    Attributes:
        title (str): The title of the product.
        image_url (str): The URL of the product image.
        price (str): The price of the product.
        asin (Optional[str]): The Amazon Standard Identification Number (ASIN) of the product, 
                              which is a unique identifier on Amazon's platform.
    """
    title: str
    image_url: str
    price: str
    asin: Optional[str] = None

    @property
    def amazon_url(self) -> str:
        return f"https://www.amazon.com/dp/{self.asin}" if self.asin else None

    def as_html(self, img_size: int = 128) -> str:
        """
        Returns an HTML representation of the product with an image thumbnail and a link to the product page.

        Parameters:
            img_size (int): Size of the image thumbnail.

        Returns:
            str: HTML string representation of the product.
        """
        html = f'<div>'
        html += f'<img src="{self.image_url}" alt="{self.title}" width="{img_size}" height="{img_size}"/>'
        if self.amazon_url:
            html += f' <a href="{self.amazon_url}">{self.title}</a>'
        else:
            html += f' {self.title}'
        html += f' - {self.price}'
        html += f'</div>'
        return html
    
class Amazon:
    """
    lookup products on amazon web site
    """
    
    def __init__(self,debug: Optional[bool] = False):
        """
        constructor
        
        Args:
            debug (bool, optional): If set to True, pretty-prints the first product div for debugging.
        """
        self.debug=debug    
            
    def extract_amazon_products(self, soup: BeautifulSoup) -> List[Product]:
        """
        Extracts product information from Amazon product listing HTML content.
    
        Args:
            soup (BeautifulSoup): Soup object of HTML content of the Amazon product listing page.
   
        Returns:
            List[Product]: A list of extracted product information as Product objects.
        """
        products = []    
        # Find all div elements that match the product listing structure
        for index, div in enumerate(soup.find_all("div", class_="puisg-row")):
            product_info = {}
            
            # Pretty-print the first product div if debug is True
            if self.debug and index == 0:
                print("Debug - First Product Div:")
                print(div.prettify())  # Pretty-print the first div
            
            # Extracting product title
            title_div = div.find("h2", class_="a-size-mini")
            if title_div and title_div.a:
                product_info['title'] = title_div.a.get_text(strip=True)
    
            # Extracting product image URL and ASIN
            image_div = div.find("div", class_="s-product-image-container")
            if image_div and image_div.a:
                product_info['image_url'] = image_div.img['src']
                link = image_div.a['href']
                asin = link.split('/dp/')[-1].split('/')[0]
                product_info['asin'] = asin
                
            # Extracting product price
            price_span = div.find("span", class_="a-price")
            if price_span and price_span.find("span", class_="a-offscreen"):
                product_info['price'] = price_span.find("span", class_="a-offscreen").get_text(strip=True)
                # Replace '\xa0€' with ' €' in price
                product_info['price'] = product_info.get('price', '').replace('\xa0', ' ')
        
    
            # Add product info to list if it contains any relevant data
            # Create a Product instance if title is present
            if 'title' in product_info:
                product = Product(
                    title=product_info['title'],
                    image_url=product_info.get('image_url', ''),
                    price=product_info.get('price', ''),
                    asin=product_info.get('asin', '')
                )
                products.append(product)
    
        return products
    
    def lookup_products(self,search_key:str):
        """
        lookup the given search key e.g. ISBN or EAN
        """
        url = f"https://www.amazon.de/s?k={search_key}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}
    
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            product_list=self.extract_amazon_products(soup)
            return product_list
        else:
            msg=f"lookup for {search_key} failed with HTML status code {response.status_code}" 
            raise Exception(msg)
