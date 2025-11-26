"""
Created on 2023-11-16
Updated on 2024-12-29
Updated on 2025-11-26 for https://github.com/WolfgangFahl/scan2wiki/issues/25

@author: wf
"""

import os
from datetime import datetime
from pathlib import Path

import requests
from ngwidgets.llm import VisionLLM
from ngwidgets.lod_grid import ListOfDictsGrid
from ngwidgets.widgets import Link
from nicegui import background_tasks, ui

from scan.amazon import Amazon
from scan.barcode import Barcode
from scan.product import Products


class BaseWebcamForm:
    """
    Base class for webcam functionality
    """

    def __init__(self, solution, webcams: dict = None):
        """
        Initialize base webcam functionality

        Args:
            solution: The solution context
            webcams: Dictionary of webcam name-url pairs
        """
        self.solution = solution
        self.scandir = solution.webserver.scandir
        self.webcams = webcams or {}

        # Default to the first webcam if available, else empty string
        self.url = next(iter(self.webcams.values())) if self.webcams else ""
        self.shot_url = f"{self.url}"
        self.image_path = None
        self.setup_base_form()

    def notify(self, msg):
        """
        Display notification in UI
        """
        with self.preview_row:
            ui.notify(msg)
        if self.solution.log_view:
            self.solution.log_view.push(msg)

    def setup_base_form(self):
        """
        Setup the base webcam form UI elements
        """
        with ui.row() as self.button_row:
            self.scan_button = ui.button("Scan", on_click=self.run_scan)
        with ui.row() as self.markup_row:
            pass
        with ui.row() as self.preview_row:
            # Simple input for URL, could be a select if self.webcams is populated
            self.webcam_input = ui.input(value=self.url, label="Webcam URL").bind_value(self, "url")
            self.image_link = ui.html().style(Link.blue)
            self.preview = ui.html()

    async def run_scan(self):
        """
        Start the scan process in the background
        """
        # Ensure shot_url updates if user changed the input
        self.shot_url = self.url
        background_tasks.create(self.perform_webcam_shot())

    async def perform_webcam_shot(self):
        """
        Perform the webcam capture
        """
        try:
            self.image_path, msg = self.save_webcam_shot()
            self.notify(msg)
            self.update_preview(self.image_path)
        except Exception as ex:
            self.solution.handle_exception(ex)

    def save_webcam_shot(self) -> tuple[str, str]:
        """
        Save image from webcam

        Returns:
            tuple: (filename, message)
        """
        image_file_name = None
        msg = "?"
        try:
            response = requests.get(self.shot_url, timeout=5)
            if response.status_code == 200:
                Path(self.scandir).mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                image_file_name = f"webcam_{timestamp}.jpg"
                image_file_path = Path(self.scandir) / image_file_name

                with open(image_file_path, "wb") as image_file:
                    image_file.write(response.content)
                msg = f"Saved webcam image to {image_file_path}"
            else:
                msg = f"Failed to fetch the webcam image. Status code: {response.status_code}"
                image_file_name = ""
        except Exception as ex:
            # Don't crash main loop, just return error
            msg = str(ex)
            image_file_name = ""

        return image_file_name, msg

    def update_preview(self, image_path: str = None):
        """
        Update the preview image in UI
        """
        try:
            with self.preview_row:
                if image_path:
                    url = f"/files/{image_path}"
                    html_markup = (
                        f"""<img src="{url}" style="width: 100%; height: auto;" />"""
                    )
                    self.image_link.content = Link.create(url, image_path)
                    self.preview.content = html_markup
                else:
                    self.preview.content = "Loading..."
        except Exception as ex:
            self.solution.handle_exception(ex)


class ProductWebcamForm(BaseWebcamForm):
    """
    Extension of WebcamForm for barcode scanning and product management
    """

    def __init__(self, solution, webcams: dict = None):
        """
        Initialize product handling functionality
        """
        super().__init__(solution, webcams)
        self.amazon = Amazon(self.solution.args.debug)
        self.product = None
        self.gtin = None
        self.products = Products()
        self.products.load_from_json()
        self.setup_product_form()
        self.update_product_grid()

    def setup_product_form(self):
        """
        Setup additional UI elements for product handling
        """
        with self.button_row:
            self.barcode_button = ui.button("Barcode", on_click=self.scan_barcode)
            self.lookup_button = ui.button("Lookup", on_click=self.lookup_gtin)
            self.add_button = ui.button("add", on_click=self.add_product)

        with self.preview_row:
            self.gtin_input = ui.input("gtin", value=self.gtin).bind_value(self, "gtin")
            self.barcode_results = ui.html("")
            self.product_grid = ListOfDictsGrid()

    def update_product_grid(self):
        """
        Update the product grid with current data
        """
        lod = self.products.get_aggrid_lod()
        self.product_grid.load_lod(lod)

    async def add_product(self):
        """
        Add current product to database
        """
        if self.product:
            self.products.add_product(self.product)
            self.products.save_to_json()
            self.update_product_grid()
            self.notify(f"Added product: {self.product.title}")

    def lookup_gtin(self):
        """
        Lookup product by GTIN/EAN
        """
        if not self.gtin:
            return

        amazon_products = self.amazon.lookup_products(self.gtin)
        if amazon_products:
            self.product = amazon_products[0]
            self.product.gtin = self.gtin
            product_html = self.product.as_html()
            msg = f"found {self.product.title} for gtin {self.gtin}"
        else:
            msg = f"No matching Amazon product found for gtin {self.gtin}."
            product_html = f"<p>{msg}</p>"

        html_markup = f"<p>Code: {self.gtin}, {product_html}</p>"
        self.notify(msg)
        self.barcode_results.content = html_markup

    async def scan_barcode(self):
        """
        Scan image for barcodes
        """
        try:
            if self.image_path:
                barcode_path = f"{self.scandir}/{self.image_path}"
                barcode_list = Barcode.decode(barcode_path)
                if barcode_list and len(barcode_list) >= 1:
                    barcode = barcode_list[0]
                    self.gtin_input.value = barcode.code
                    msg = f"barcode {barcode.code} type {barcode.type} found"
                else:
                    msg = "No barcodes found."
            else:
                msg = "No image to scan for barcodes."
            self.notify(msg)
        except Exception as ex:
            self.solution.handle_exception(ex)


class AIWebcamForm(BaseWebcamForm):
    """
    Extension of WebcamForm with AI capabilities via ngwidgets.VisionLLM
    """

    def __init__(self, solution, webcams: dict):
        """
        Initialize AI functionality
        """
        super().__init__(solution, webcams)
        self.args = solution.args

        # Configure VisionLLM to use OpenRouter by default if keys are present
        # This replaces the need for local scp/ssh since we use direct upload/base64
        self.llm = VisionLLM(
            base_url="https://openrouter.ai/api/v1",
            model="google/gemini-2.0-flash-001"
        )
        self.setup_ai_form()

    def setup_ai_form(self):
        """
        Setup AI-specific UI elements
        """
        with self.button_row:
            self.analyze_button = ui.button("Analyze", on_click=self.analyze_image)
        with self.markup_row:
            self.markup_result = ui.html("Markup will show here")

    async def analyze_image(self):
        """
        Start the image analysis process in the background
        """
        background_tasks.create(self.perform_analysis())

    def show_markup(self, msg: str, with_notify: bool = True):
        #  display results
        with self.markup_row:
            self.markup_result.content = f"<pre>{msg}</pre>"
        if with_notify:
            self.notify(msg)

    async def perform_analysis(self):
        """
        Perform the AI analysis of the image using VisionLLM
        """
        try:
            if not self.llm.available():
                self.notify("LLM API Key not found (OpenAI or OpenRouter).")
                return

            if not self.image_path:
                self.notify("No image available for analysis")
                return

            # Construct full local path
            full_image_path = f"{self.scandir}/{self.image_path}"

            if not os.path.exists(full_image_path):
                self.notify(f"File not found: {full_image_path}")
                return

            msg = "Starting LLM analysis ..."
            self.show_markup(msg)

            prompt = """
            Please OCR the image and format the response for MediaWiki markup.
            The result will be copied to a page directly so do not wrap or add comments.
            """

            # VisionLLM now handles local paths via Base64 encoding automatically
            markup = self.llm.analyze_image(image_path=full_image_path, prompt_text=prompt)
            self.show_markup(markup, with_notify=False)

        except Exception as ex:
            self.solution.handle_exception(ex)