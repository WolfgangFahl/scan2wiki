"""
Created on 2023-11-16

@author: wf
"""

import json
from typing import Dict, List, Optional
import os
from os.path import dirname,exists,expanduser
from dataclasses import dataclass
from ngwidgets.widgets import Link

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
    ean: Optional[str] = None

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

class Products:
    """
    Class to handle/manage product instances and make those persistent.

    Attributes:
        store_path (str): The file path where products are stored as JSON.
        products (List[Product]): List of product instances.
        products_by_asin (Dict[str, Product]): Dictionary mapping ASIN to products.
        products_by_ean (Dict[str, Product]): Dictionary mapping EAN to products.
    """

    def __init__(self, store_path: str = None):
        """
        Initialize the Products instance.

        Args:
            store_path (str, optional): The file path where products are stored as JSON.
                                       Defaults to ~/.scan2wiki/products.json.
        """
        self.store_path = store_path or expanduser("~/.scan2wiki/products.json")
        self.clear()

    def clear(self):
        """
        Clears the current product list and the associated mappings.
        """
        self.products = []
        self.products_by_asin = {}
        self.products_by_ean = {}

    def add_product(self, product: Product):
        """
        Adds a product to the product list and updates the mappings.

        Args:
            product (Product): The product instance to add.
        """
        self.products.append(product)
        if product.ean:
            self.products_by_ean[product.ean] = product
        if product.asin:
            self.products_by_asin[product.asin] = product
            
    def delete_product(self, asin: str):
        """
        Delete a product with the given ASIN.

        Args:
            asin (str): The ASIN of the product to delete.
        """
        # Delete the product from the products list
        if asin in self.products.products_by_asin:
            product = self.products.products_by_asin[asin]
            self.products.products.remove(product)
            del self.products.products_by_asin[asin]
            if product.ean and product.ean in self.products.products_by_ean:
                del self.products.products_by_ean[product.ean]
            self.products.save_to_json()  # Save the updated product list
 
    def get_aggrid_lod(self) -> List[Dict[str, str]]:
        """
        Generates a list of dictionaries for ag-Grid representation of the products.

        Returns:
            List[Dict[str, str]]: List of product information formatted for ag-Grid.
        """
        lod = []
        for index, product in enumerate(self.products, start=1):
            product_dict = {
                "#": str(index),
                "Product": product.as_html(),
                "ASIN": Link.create(product.amazon_url, product.asin) if product.asin else "",
                "Title": product.title,
                "EAN": product.ean if product.ean else "",
                "Price": product.price
            }
            lod.append(product_dict)
        return lod

    def save_to_json(self, filename: str = None):
        """
        Saves the current list of products to a JSON file.

        Args:
            filename (str, optional): The filename where to save the JSON data.
                                      Defaults to the instance's store_path attribute.
        """
        
        filename = filename or self.store_path
        # Ensure the directory for the store_path exists
        directory = dirname(filename)
        if not exists(directory):
            os.makedirs(directory, exist_ok=True)
            
        product_data = [product.__dict__ for product in self.products]
        with open(filename, 'w') as file:
            json.dump(product_data, file, indent=2)

    def load_from_json(self, filename: str = None):
        """
        Loads products from a JSON file and updates the current list and mappings.

        Args:
            filename (str, optional): The filename from which to load the JSON data.
                                      Defaults to the instance's store_path attribute.
        """
        filename = filename or self.store_path
        with open(filename, 'r') as file:
            product_data = json.load(file)
        for data in product_data:
            self.add_product(Product(**data))
