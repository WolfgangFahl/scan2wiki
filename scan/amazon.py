"""
Created on 12023-11-16

@author: wf
"""
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List

@dataclass
class Product:
    """
    Data class representing a product.

    Attributes:
        title (str): Title of the product.
        image_url (str): URL of the product image.
        price (str): Price of the product.
    """
    title: str
    image_url: str
    price: str
    
class Amazon:
    """
    lookup products on amazon web site
    """
    
    @classmethod
    def extract_amazon_products(cls, soup: BeautifulSoup) -> List[Product]:
        """
        Extracts product information from Amazon product listing HTML content.
    
        Args:
            soup (BeautifulSoup): Soup object of HTML content of the Amazon product listing page.
    
        Returns:
            List[Product]: A list of extracted product information as Product objects.
        """
        products = []    
        # Find all div elements that match the product listing structure
        for div in soup.find_all("div", class_="puisg-row"):
            product_info = {}
            
            # Extracting product title
            title_div = div.find("h2", class_="a-size-mini")
            if title_div and title_div.a:
                product_info['title'] = title_div.a.get_text(strip=True)
    
            # Extracting product image URL
            image_div = div.find("div", class_="s-product-image-container")
            if image_div and image_div.img:
                product_info['image_url'] = image_div.img['src']
            
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
                    price=product_info.get('price', '')
                )
                products.append(product)
    
        return products
    
    @classmethod
    def lookup_products(cls,search_key:str):
        """
        lookup the given search key e.g. ISBN or EAN
        """
        url = f"https://www.amazon.de/s?k={search_key}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}
    
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            product_list=cls.extract_amazon_products(soup)
            return product_list
        else:
            msg=f"lookup for {search_key} failed with HTML status code {response.status_code}" 
            raise Exception(msg)
