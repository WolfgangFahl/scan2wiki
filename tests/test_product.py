"""
Created on 2023-11-16

@author: wf
"""
from ngwidgets.basetest import Basetest
from scan.product import Product, Products
import tempfile
import os

class TestProduct(Basetest):
    """
    Test the product handling.
    """

    def test_products(self):
        """
        Test adding products, storing and reloading them.
        """
        debug=self.debug
        debug=True
        # Test data setup
        examples = [
            Product(title="The Beatles - A Hard Day's Night", 
            image_url="https://m.media-amazon.com/images/I/81m01dZR2UL._AC_UY218_.jpg", 
            price="4,99 €", asin="B00KHK1SW2",
            ean="4020628887711")
        ]

        use_temp=False
        if use_temp:
            # Creating Products instance
            temp_dir = tempfile.mkdtemp()  # Create a temporary directory
            temp_file = os.path.join(temp_dir, "temp_products.json")
        else:
            temp_file=None    
        products = Products(store_path=temp_file)

        # Add example products
        for product in examples:
            if debug:
                print(product)
            products.add_product(product)

        # Save the products to a JSON file
        products.save_to_json()

        # Optionally print the saved JSON file content for debugging
        if debug:
            with open(products.store_path, 'r') as file:
                print("Saved JSON content:", file.read())

        # Clear current products and load them back from the file
        products.clear()
        products.load_from_json()

        # Check if the loaded products match the added products
        for expected_product in examples:
            loaded_product = products.products_by_ean[expected_product.ean]
            self.assertEqual(expected_product.title, loaded_product.title)
            self.assertEqual(expected_product.image_url, loaded_product.image_url)
            self.assertEqual(expected_product.price, loaded_product.price)
            self.assertEqual(expected_product.asin, loaded_product.asin)

        # Clean up - remove the temporary directory if not in debug mode
        if not debug:
            os.remove(temp_file)
            os.rmdir(temp_dir)



    