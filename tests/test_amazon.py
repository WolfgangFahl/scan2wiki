"""
Created on 2023-11-16

@author: wf
"""

from os.path import expanduser

from ngwidgets.basetest import Basetest

from scan.amazon import Amazon, Product
from scan.product import Products


class TestAmazon(Basetest):
    """
    test the amazon search
    """

    def testBooks(self):
        """ """
        if self.inPublicCI():
            return
        debug = False
        yaml_path = expanduser("~/.scan2wiki/books.yaml")
        books = Products.ofYaml(yaml_path=yaml_path)
        amazon = Amazon(debug=debug)
        for book in books.products:
            abooks = amazon.lookup_products(book.title)
            if len(abooks) > 0:
                abook = abooks[0]
                print(book.title)
                print(abook.amazon_url)
                print(abook.image_url)
                print(abook.details)

    def testAmazon(self):
        """
        Test Amazon lookup to ensure it returns correct product details.

        This test checks if the Amazon product lookup returns the expected
        product details for a given search key.
        """
        if not self.inPublicCI():
            # Test data setup
            searches = {
                "Security Engineering – A Guide to Building Dependable Distributed Systems": Product(
                    title="Security Engineering: A Guide to Building Dependable Distributed Systems",
                    image_url="https://m.media-amazon.com/images/I/81JsRNw-LWL._AC_UY218_.jpg",
                    price="50,99 €",
                ),
                "4020628887711": Product(
                    title="The Beatles - A Hard Day's Night",
                    image_url="https://m.media-amazon.com/images/I/81m01dZR2UL._AC_UY218_.jpg",
                    price="59,99 €",
                ),  # Note the space instead of '\xa0'
            }
            debug = self.debug
            debug = False
            verbose = True
            amazon = Amazon(debug=debug)
            # Testing each search key
            for search_key, expected_product in searches.items():
                products = amazon.lookup_products(search_key)
                self.assertTrue(
                    products, f"No products found for search key: {search_key}"
                )
                product = products[0]
                if verbose:
                    print(product)
                self.assertTrue(expected_product.title in product.title)
                self.assertEqual(product.image_url, expected_product.image_url)
                self.assertEqual(product.price, expected_product.price)
