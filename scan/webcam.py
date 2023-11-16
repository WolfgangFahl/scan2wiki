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
from scan.barcode import Barcode
from scan.amazon import Amazon

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
        self.setup_form()
        self.amazon=Amazon(self.webserver.debug)

    def notify(self, msg):
        ui.notify(msg)
        if self.webserver.log_view:
            self.webserver.log_view.push(msg)

    async def run_scan(self):
        """
        Start the scan process in the background.
        """
        _, scan_coro = self.task_handler.execute_in_background(self.save_webcam_shot)
        self.image_path = await scan_coro()
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

            self.notify(msg)
        except Exception as ex:
            self.webserver.handle_exception(ex)

        return image_file_name

    def setup_form(self):
        """
        Setup the webcam form
        """
        # Button to refresh or scan the video stream
        self.scan_button = ui.button("Scan", on_click=self.run_scan)
        self.barcode_button = ui.button("Barcode", on_click=self.scan_barcode)
        # HTML container for the webcam video stream
        self.webcam_input = ui.input(value=self.url)
        self.image_link = ui.html().style(self.blue_link)
        self.barcode_results = ui.html("")
        self.preview = ui.html()

    async def scan_barcode(self):
        """
        Scan for barcodes in the most recently saved webcam image and look up products on Amazon.
        """
        msg = "No image to scan for barcodes."
        if self.image_path:
            barcode_path = f"{self.scandir}/{self.image_path}"
            barcode_list = Barcode.decode(barcode_path)
            if barcode_list:
                results = []
                for barcode in barcode_list:
                    # Perform Amazon lookup for each barcode
                    amazon_products = self.amazon.lookup_products(barcode.code)
                    if amazon_products:
                        # Assuming you want to display the first product found for each barcode
                        product = amazon_products[0]
                        product_details = f"Product: {product.title}, Price: {product.price}, ASIN: {product.asin}"
                    else:
                        product_details = "No matching Amazon product found."
    
                    barcode_result = f"Code: {barcode.code}, Type: {barcode.type}, {product_details}"
                    results.append(barcode_result)
    
                msg = "\n".join(results)
            else:
                msg = "No barcodes found."
        else:
            msg = "No image to scan for barcodes."
    
        self.notify(msg)
        html_markup = f"<pre>{msg}</pre>"
        self.barcode_results.content = html_markup


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
