"""
Created on 2023-11-16

@author: wf
"""
from nicegui import ui
import requests
from pathlib import Path
from datetime import datetime
from ngwidgets.widgets import Link
from ngwidgets.background import BackgroundTaskHandler
from ngwidgets.lod_grid import ListOfDictsGrid
from scan.barcode import Barcode
from scan.amazon import Amazon
from scan.product import Products

class WebcamForm:
    """
    allow scanning pictures from a webcam
    """

    def __init__(self, webserver, default_url: str):
        """
        construct me
        """
        self.task_handler = BackgroundTaskHandler()
        # @TODO refactor to link
        self.red_link = "color: red;text-decoration: underline;"
        self.blue_link = "color: blue;text-decoration: underline;"

        self.webserver = webserver
        self.scandir = webserver.scandir
        self.url = default_url
        self.shot_url = f"{self.url}/shot.jpg"
        self.image_path = None
        self.amazon=Amazon(self.webserver.debug)
        self.product=None
        self.gtin=None
        self.products = Products()  # Initialize the Products instance
        self.products.load_from_json()  # Load existing products
        self.setup_form()
        self.update_product_grid()

    def notify(self, msg):
        ui.notify(msg)
        if self.webserver.log_view:
            self.webserver.log_view.push(msg)

    async def run_scan(self):
        """
        Start the scan process in the background.
        """
        _, scan_coro = self.task_handler.execute_in_background(self.save_webcam_shot)
        self.image_path,msg = await scan_coro()
        self.notify(msg)
        self.update_preview(self.image_path)

    def save_webcam_shot(self) -> str:
        """
        Fetches an image from the webcam URL and saves it with a timestamp in the specified directory.

        Returns:
            str: The file name of the saved webcam image, or an error message if the fetch failed.
        """
        image_file_name = None
        try:
            shot_url=f"{self.url}/shot.jpg"
            response = requests.get(shot_url)
            if response.status_code == 200:
                # Ensure the scandir directory exists
                Path(self.scandir).mkdir(parents=True, exist_ok=True)
                image_data = response.content
                # Get current date and time without timezone information
                timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                # Define the full path to save the image
                image_file_name = f"webcam_{timestamp}.jpg"
                image_file_path = Path(self.scandir) / image_file_name
                # Write the image data to the file system
                with open(image_file_path, "wb") as image_file:
                    image_file.write(image_data)
                msg = f"Saved webcam image to {image_file_path}"
            else:
                msg = f"Failed to fetch the webcam image. Status code: {response.status_code}"
                image_file_name = ""

        except Exception as ex:
            self.webserver.handle_exception(ex)

        return image_file_name,msg

    def setup_form(self):
        """
        Setup the webcam form
        """
        # Button to refresh or scan the video stream
        self.scan_button = ui.button("Scan", on_click=self.run_scan)
        self.barcode_button = ui.button("Barcode", on_click=self.scan_barcode)
        self.lookup_button = ui.button("Lookup",on_click=self.lookup_gtin)
        self.add_button = ui.button("add", on_click=self.add_product)
        self.webcam_input = ui.input(value=self.url)
        self.image_link = ui.html().style(self.blue_link)
        self.gtin_input=ui.input("gtin",value=self.gtin).bind_value(self,"gtin")
        self.barcode_results = ui.html("")
        self.product_grid = ListOfDictsGrid() 
        # HTML container for the webcam snap shot
        self.preview = ui.html()
        
    def update_product_grid(self):
        """
        Update the product grid with the current products.
        """
        lod = self.products.get_aggrid_lod()
        self.product_grid.load_lod(lod)   
        
    async def add_product(self):
        """
        add the given product
        """
        self.products.add_product(self.product)
        self.products.save_to_json()  # Save the updated product list
        self.update_product_grid()  # Update the product grid   
 
    def lookup_gtin(self):
        """
        lookup the  global trade identification number e.g. ean
        """ 
        if not self.gtin:
            return
        # Perform Amazon lookup for gtin
        amazon_products = self.amazon.lookup_products(self.gtin)
        if amazon_products:
            # Assuming you want to display the first product found for each barcode
            self.product = amazon_products[0]
            self.product.gtin=self.gtin
            product_html = self.product.as_html()
            product_details = product_html
            msg=f"found {self.product.title} for gtin {self.gtin}"
        else:
            msg=f"No matching Amazon product found for gtin {self.gtin}."
            product_details = f"<p>{msg}</p>"

        html_markup = f"<p>Code: {self.gtin}, {product_details}</p>"
        self.notify(msg)    
        self.barcode_results.content = html_markup
 
    async def scan_barcode(self):
        """
        Scan for barcodes in the most recently saved webcam image and look up products on Amazon.
        """
        try:
            if self.image_path:
                barcode_path = f"{self.scandir}/{self.image_path}"
                barcode_list = Barcode.decode(barcode_path)
                if barcode_list and len(barcode_list)>=1:
                    barcode=barcode_list[0]
                    self.gtin_input.value=barcode.code
                    msg = f"barcode {barcode.code} type {barcode.type} found"              
                else:
                    msg = "No barcodes found."
            else:
                msg = "No image to scan for barcodes."     
            self.notify(msg)
        except Exception as ex:
            self.webserver.handle_exception(ex)

    def update_preview(self, image_path: str = None):
        """
        Update the preview with the current URL of the webcam.
        """
        if image_path:
            url = f"/files/{image_path}"
            html_markup = f"""<img src="{url}" style="width: 100%; height: auto;" />"""
            self.image_link.content = Link.create(url, image_path)
            self.preview.content = html_markup
        else:
            self.preview.content = "Loading..."
