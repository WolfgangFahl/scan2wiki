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
from ngwidgets.lod_grid import ListOfDictsGrid
from ngwidgets.widgets import Link
from nicegui import background_tasks,ui
from ngwidgets.image_cropper import ImageCropper

from ngwidgets.ai_tasks import AITasks
from scan.amazon import Amazon
from scan.barcode import Barcode
from scan.product import Products


class BaseWebcamForm:
    """
    Base class for webcam functionality
    """

    def __init__(self, solution, webcams: dict = None, path:str=None):
        """
        Initialize base webcam functionality

        Args:
            solution: The solution context
            webcams: Dictionary of webcam name-url pairs
            path: Optional path to preload an existing image
        """
        self.solution = solution
        self.scans=self.solution.webserver.scans
        self.scandir = solution.webserver.scandir
        self.webcams = webcams or {}

        # Default to the first webcam if available, else empty string
        self.url = next(iter(self.webcams.values())) if self.webcams else ""
        self.shot_url = f"{self.url}"
        self.image_path = path
        self.cropper=ImageCropper(solution=self.solution)
        self.setup_base_form()
        if self.image_path:
            background_tasks.create(self.update_image_preview())

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
        try:
            with ui.row() as self.button_row:
                self.scan_button = ui.button("Scan", icon="camera",on_click=self.run_scan)
                self.delete_button = ui.button("Delete", icon="delete", on_click=self.delete)
            with ui.row() as self.markup_row:
                pass
            with ui.row() as self.preview_row:
                # If predefined webcams exist, show a selector
                if self.webcams:
                    # The select shows friendly names (keys) and stores the URL (values)
                    # Swap dict: {url: name} so select displays names but stores URLs
                    swapped = {url: name for name, url in self.webcams.items()}

                    self.webcam_select = self.solution.add_select(
                        title="Webcam",
                        selection=swapped,
                    ).bind_value(
                        self, "url"
                    )  # keep in sync with self.url

                # Always show manual input for custom URLs
                self.webcam_input = (
                    ui.input(
                        value=self.url, label="Webcam URL", placeholder="http(s)://..."
                    )
                    .bind_value(self, "url")  # bound to the same attribute as the select
                    .props("size=60")
                )
                self.cropper.setup_ui(
                    container=self.preview_row,
                    image_url="")
                self.image_link = ui.html().style(Link.blue)
        except Exception as ex:
            self.solution.handle_exception(ex)

    async def run_scan(self):
        """
        Start the scan process in the background
        """
        # Ensure shot_url updates if user changed the input
        self.shot_url = self.url
        background_tasks.create(self.perform_webcam_shot())

    async def delete(self) -> None:
        """
        Deletes the currently selected image file after user confirmation.
        """
        try:
            if not self.image_path:
                return

            if await self.solution.confirm(f"Delete {self.image_path}?"):
                # Delegate deletion of image and potential sidecar txt to the Scans service
                self.scans.delete(self.image_path, with_txt=True)

                self.notify(f"Deleted {self.image_path}")
                self.image_path = None
                self.update_preview(None)

        except Exception as ex:
            self.solution.handle_exception(ex)



    async def update_image_preview(self):
        self.update_preview(self.image_path)

    async def perform_webcam_shot(self):
        """
        Perform the webcam capture
        """
        try:
            self.image_path, msg = self.save_webcam_shot()
            self.notify(msg)
            await self.update_image_preview()
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
                self.cropper.file_path=image_file_path
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
                    # Set the file_path for the cropper so rotate/crop operations work immediately
                    self.cropper.file_path = str(Path(self.scandir) / image_path)
                    # External url
                    url = f"/files/{image_path}"
                    self.cropper.set_source(url)
                    self.image_link.content = Link.create(url, image_path)
                else:
                    self.cropper.set_source("")
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
            self.barcode_button = ui.button("Barcode",icon="qr_code_scanner", on_click=self.scan_barcode)
            self.lookup_button = ui.button("Lookup", icon="search", on_click=self.lookup_gtin)
            self.add_button = ui.button("add", icon="add", on_click=self.add_product)

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

    def __init__(self, solution, webcams: dict, path: str = None):
        """
        Initialize AI functionality

        Args:
            solution: The solution context
            webcams: Dictionary of webcam name-url pairs
            path: Optional path to preload an existing image
        """
        super().__init__(solution, webcams, path)
        self.args = solution.args
        examples_path = Path(__file__).parent.parent / "scan2wiki_examples"
        yaml_file_path = str(examples_path / "ai_tasks.yaml")
        self.ai_tasks = AITasks.get_instance(yaml_file_path=yaml_file_path)
        self.selected_task = (
            next(iter(self.ai_tasks.tasks)) if self.ai_tasks.tasks else None
        )
        self.selected_model = (
            next(iter(self.ai_tasks.models)) if self.ai_tasks.models else "gpt-4o-mini"
        )
        self.setup_ai_form()

    def setup_ai_form(self):
        """
        Setup AI-specific UI elements
        """
        try:
            with self.button_row:
                self.analyze_button = ui.button("Analyze",icon="analytics", on_click=self.analyze_image)
                self.save_button = ui.button("Save", icon="save", on_click=self.save_analysis)
            with self.markup_row:
                # Selector for AI tasks (prompts)
                task_selection = {
                    task_name: task_config.description or task_name
                    for task_name, task_config in self.ai_tasks.tasks.items()
                }
                self.task_select = self.solution.add_select(
                    title="AI Task",
                    selection=task_selection,
                ).bind_value(self, "selected_task")

                # Selector for models
                model_selection = {
                    model_name: model_config.name
                    for model_name, model_config in self.ai_tasks.models.items()
                }
                self.model_select = self.solution.add_select(
                    title="Model",
                    selection=model_selection,
                ).bind_value(self, "selected_model")

                self.markup_result = ui.editor(placeholder="Markup will show here")
                pass
        except Exception as ex:
            self.solution.handle_exception(ex)

    async def analyze_image(self):
        """
        Start the image analysis process in the background
        """
        background_tasks.create(self.perform_analysis())

    def show_markup(self, msg: str, with_notify: bool = True):
        # display results
        with self.markup_row:
            self.markup_result.value = f"<pre>{msg}</pre>"
        if with_notify:
            self.notify(msg)

    async def save_analysis(self):
        """
        Save the current editor content to a corresponding .txt file
        """
        try:
            if not self.image_path:
                self.notify("No image associated with current view.")
                return

            # Construct paths
            image_file_path = Path(self.scandir) / self.image_path
            # Change extension to .txt
            txt_file_path = image_file_path.with_suffix(".txt")

            # Get content from the editor
            content = self.markup_result.value

            if content:
                with open(txt_file_path, "w", encoding="utf-8") as text_file:
                    text_file.write(content)
                self.notify(f"Saved analysis to {txt_file_path.name}")
            else:
                self.notify("No content to save.")

        except Exception as ex:
            self.solution.handle_exception(ex)


    async def perform_analysis(self):
        """
        Perform the AI analysis of the image using AITasks
        """
        try:
            if self.selected_task is None:
                self.notify("No AI task selected.")
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

            # Perform the task using AITasks
            params = {
                "image_path": full_image_path
            }  # Add more params if needed for prompt templating
            markup = self.ai_tasks.perform_task(
                model_name=self.selected_model,
                task_name=self.selected_task,
                params=params,
            )
            self.show_markup(markup, with_notify=False)

        except Exception as ex:
            self.solution.handle_exception(ex)
