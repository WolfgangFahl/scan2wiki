"""
Created on 2023-11-16

@author: wf
"""

from dataclasses import dataclass, field
from os.path import expanduser
from typing import Dict, List, Optional

from basemkit.yamlable import lod_storable
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
    image_url: Optional[str] = None
    price: Optional[str] = None
    asin: Optional[str] = None
    gtin: Optional[str] = None
    details: Dict[str, str] = field(default_factory=dict)

    @property
    def amazon_url(self) -> str:
        return f"https://www.amazon.de/dp/{self.asin}" if self.asin else None

    def as_html(self, img_size: int = 128) -> str:
        """
        Returns an HTML representation of the product with an image thumbnail and a link to the product page.

        Parameters:
            img_size (int): Size of the image thumbnail.

        Returns:
            str: HTML string representation of the product.
        """
        html = f"<div>"
        html += f'<img src="{self.image_url}" alt="{self.title}" width="{img_size}" height="{img_size}"/>'
        if self.amazon_url:
            html += f' <a href="{self.amazon_url}">{self.title}</a>'
        else:
            html += f" {self.title}"
        if self.gtin:
            html += f"Code: {self.gtin}"
        html += f" - {self.price}"
        html += f"</div>"
        return html


@lod_storable
class Products:
    """
    Class to handle/manage product instances and make those persistent.

    Attributes:
        store_path (str): The file path where products are stored as JSON.
        products (List[Product]): List of product instances.
        products_by_asin (Dict[str, Product]): Dictionary mapping ASIN to products.
        products_by_gtin (Dict[str, Product]): Dictionary mapping gtin to products.
    """

    products: List[Product] = field(default_factory=list)

    # transient indexes (not persisted)
    products_by_asin: Dict[str, Product] = field(
        init=False, repr=False, default_factory=dict
    )
    products_by_gtin: Dict[str, Product] = field(
        init=False, repr=False, default_factory=dict
    )

    def __post_init__(self):
        """
        Initialize the Products instance.

        Args:
            store_path (str, optional): The file path where products are stored as JSON.
                                       Defaults to ~/.scan2wiki/products.json.
        """
        self.products_by_asin = {p.asin: p for p in self.products if p.asin}
        self.products_by_gtin = {p.gtin: p for p in self.products if p.gtin}

    @classmethod
    def store_path(cls) -> str:
        yaml_path = expanduser("~/.scan2wiki/products.yaml")
        return yaml_path

    @classmethod
    def ofYaml(cls, yaml_path: str = None) -> "Products":
        if yaml_path is None:
            yaml_path = cls.store_path()
        products = cls.load_from_yaml_file(yaml_path)
        return products

    def add_product(self, product: Product):
        """
        Adds a product to the product list and updates the mappings.
        If a product with the same ASIN already exists, it updates the existing record.

        Args:
            product (Product): The product instance to add.
        """
        # Update product if it already exists in the by_asin list
        if product.asin and product.asin in self.products_by_asin:
            existing_product = self.products_by_asin[product.asin]
            existing_product.title = product.title
            existing_product.image_url = product.image_url
            existing_product.price = product.price
            existing_product.gtin = product.gtin
        else:
            # Add the product to the list and mappings
            self.products.append(product)
            if product.asin:
                self.products_by_asin[product.asin] = product
            if product.gtin:
                self.products_by_gtin[product.gtin] = product

        # Sort the products list by ASIN
        self.products.sort(key=lambda p: p.asin if p.asin else "")

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
            if product.gtin and product.gtin in self.products.products_by_gtin:
                del self.products.products_by_gtin[product.gtin]
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
                "ASIN": (
                    Link.create(product.amazon_url, product.asin)
                    if product.asin
                    else ""
                ),
                "Title": product.title,
                "gtin": product.gtin if product.gtin else "",
                "Price": product.price,
            }
            lod.append(product_dict)
        return lod
