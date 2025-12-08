"""
Created on 2025-12-08

@author: wf
"""

from nicegui import events, ui
from PIL import Image

class ImageCropper:
    """
    A NiceGUI-based interactive image cropper.
    Allows users to draw a box on an image to define crop coordinates.
    """

    def __init__(self):
        # Crop State
        self.crop_x: int = 0
        self.crop_y: int = 0
        self.crop_width: int = 0
        self.crop_height: int = 0

        # Dragging State for UI
        self.dragging: bool = False
        self.start_x: float = 0
        self.start_y: float = 0

        # References
        self.interactive_view: ui.interactive_image = None
        pass

    def setup_ui(self, image_url: str):
        """
        Sets up the UI elements: the coordinate inputs and the interactive image.
        """
        # Coordinate display
        with ui.row().classes("items-center"):
            ui.label("Crop Area:")
            with ui.row():
                ui.number(label="X", value=0).bind_value(self, "crop_x").props("size=5 readonly")
                ui.number(label="Y", value=0).bind_value(self, "crop_y").props("size=5 readonly")
                ui.number(label="W", value=0).bind_value(self, "crop_width").props("size=5 readonly")
                ui.number(label="H", value=0).bind_value(self, "crop_height").props("size=5 readonly")

            # Reset button convenient to have nearby
            ui.button(icon="crop_free", on_click=self.reset_crop).props("flat round color=warning").tooltip("Reset Crop")

        # Interactive Image implementation
        self.interactive_view = ui.interactive_image(
            image_url,
            on_mouse=self.handle_mouse,
            events=["mousedown", "mousemove", "mouseup"],
            cross=True,
        ).classes("w-full")

    def set_source(self, source: str):
        """Updates the image source URL."""
        if self.interactive_view:
            self.interactive_view.set_source(source)

    def handle_mouse(self, e: events.MouseEventArguments):
        """
        Handles mouse events to draw a crop rectangle on the interactive image.
        """
        if e.type == "mousedown":
            self.dragging = True
            self.start_x = e.image_x
            self.start_y = e.image_y

        elif e.type == "mousemove":
            if self.dragging:
                self.update_crop_selection(e.image_x, e.image_y)

        elif e.type == "mouseup":
            self.dragging = False
            self.update_crop_selection(e.image_x, e.image_y)

    def update_crop_selection(self, current_x: float, current_y: float):
        """
        Calculates the rectangle coordinates based on start and current pointers,
        updates state variables, and draws the SVG overlay.
        """
        # Calculate top-left corner and dimensions
        x = min(self.start_x, current_x)
        y = min(self.start_y, current_y)
        w = abs(self.start_x - current_x)
        h = abs(self.start_y - current_y)

        # Update persistent crop variables (convert to int for PIL)
        self.crop_x = int(x)
        self.crop_y = int(y)
        self.crop_width = int(w)
        self.crop_height = int(h)

        # Update the visual SVG overlay
        self.interactive_view.content = (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'fill="none" stroke="red" stroke-width="2" />'
        )

    def reset_crop(self):
        """Resets crop variables and clears SVG overlay."""
        self.crop_x = 0
        self.crop_y = 0
        self.crop_width = 0
        self.crop_height = 0
        if self.interactive_view:
            self.interactive_view.content = ""

    def apply_crop(self, image: Image.Image) -> Image.Image:
        """
        Applies the current crop selection to a PIL Image object.
        Returns the original image if no crop is selected.
        """
        apply_image=image
        if self.crop_width > 0 and self.crop_height > 0:
            box = (
                self.crop_x,
                self.crop_y,
                self.crop_x + self.crop_width,
                self.crop_y + self.crop_height,
            )
            apply_image=image.crop(box)
        return apply_image