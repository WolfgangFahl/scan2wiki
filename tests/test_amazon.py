"""
Created on 2023-11-16

@author: wf
"""
from ngwidgets.basetest import Basetest
from scan.amazon import Amazon, Product

class TestAmazon(Basetest):
    """
    test the amazon search
    """
    
    def test_amazon(self):
        """
        Test Amazon lookup to ensure it returns correct product details.

        This test checks if the Amazon product lookup returns the expected
        product details for a given search key.
        """
        if not self.inPublicCI():
            # Test data setup
            searches = {
                "4020628887711": Product(title="The Beatles - A Hard Day's Night", 
                                         image_url="https://m.media-amazon.com/images/I/81m01dZR2UL._AC_UY218_.jpg", 
                                         price="4,99 €")  # Note the space instead of '\xa0'
            }
            debug=self.debug
            #debug=True
            amazon=Amazon(debug=debug)
            # Testing each search key
            for search_key, expected_product in searches.items():
                products = amazon.lookup_products(search_key)
                self.assertTrue(products, f"No products found for search key: {search_key}")
                product=products[0]
                if debug:
                    print(product)
                self.assertEqual(product.title, expected_product.title)
                self.assertEqual(product.image_url, expected_product.image_url)
                self.assertEqual(product.price, expected_product.price)
                
