"""
Created on 2026-08-20

cam2web - webcam emulator module of scan2wiki
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from fastapi.responses import HTMLResponse, Response, StreamingResponse
from ngwidgets.input_webserver import InputWebserver, InputWebSolution
from ngwidgets.webserver import WebserverConfig
from nicegui import Client, app, ui

from scan.version import Version


class Camera:
    """
    camera backend serving JPEG frames and stills
    """

    def __init__(self):
        self.lock = threading.Lock()

    def claim(self) -> bool:
        """
        claim the camera for a single client

        Returns:
            bool: True if the camera was claimed
        """
        claimed = self.lock.acquire(blocking=False)
        return claimed

    def release(self):
        """
        release the camera
        """
        if self.lock.locked():
            self.lock.release()

    def preview_frame(self) -> bytes:
        """
        get a single live view JPEG frame
        """
        raise NotImplementedError

    def capture_still(self) -> bytes:
        """
        take a picture and return it as JPEG bytes
        """
        raise NotImplementedError


class MockCamera(Camera):
    """
    hardware-free camera for testing - renders frames via PyMuPDF
    """

    def __init__(self):
        super().__init__()
        self.frame_no = 0

    def render(self, text: str) -> bytes:
        """
        render the given text as a JPEG image

        Args:
            text (str): the text to render

        Returns:
            bytes: JPEG image data
        """
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=768, height=512)
        page.insert_text((40, 260), text, fontsize=36)
        pix = page.get_pixmap()
        jpeg_bytes = pix.tobytes("jpeg")
        doc.close()
        return jpeg_bytes

    def preview_frame(self) -> bytes:
        self.frame_no += 1
        return self.render(f"mock preview {self.frame_no}")

    def capture_still(self) -> bytes:
        return self.render("mock still")


class GPhoto2Camera(Camera):
    """
    gphoto2 camera backend using the python-gphoto2 library
    """

    def __init__(self):
        super().__init__()
        self.camera = None
        self.mode = None  # "preview" or "still"

    @staticmethod
    def macos_workaround():
        """
        on macOS the ptpcamerad daemon claims the USB device -
        kill it so gphoto2 can access the camera
        """
        if sys.platform == "darwin":
            subprocess.run(
                ["killall", "-9", "ptpcamerad"],
                capture_output=True,
                check=False,
            )

    def open(self):
        """
        initialize the gphoto2 camera connection
        """
        import gphoto2 as gp

        self.macos_workaround()
        self.camera = gp.Camera()
        self.camera.init()

    def close(self):
        """
        close the gphoto2 camera connection
        """
        if self.camera:
            self.camera.exit()
            self.camera = None
        self.mode = None

    def switch_mode(self, mode: str):
        """
        switch between live view and picture taking - on macOS
        the camera must be reclaimed on each switch

        Args:
            mode (str): "preview" or "still"
        """
        if self.mode != mode:
            if self.mode is not None:
                self.close()
                self.macos_workaround()
            if self.camera is None:
                self.open()
            self.mode = mode

    def preview_frame(self) -> bytes:
        import gphoto2 as gp

        self.switch_mode("preview")
        camera_file = self.camera.capture_preview()
        file_data = camera_file.get_data_and_size()
        return bytes(file_data)

    def capture_still(self) -> bytes:
        import gphoto2 as gp

        self.switch_mode("still")
        file_path = self.camera.capture(gp.GP_CAPTURE_IMAGE)
        camera_file = self.camera.file_get(
            file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL
        )
        file_data = camera_file.get_data_and_size()
        return bytes(file_data)

    def release(self):
        self.close()
        super().release()


@dataclass
class Cam2WebVersion(Version):
    """
    Version handling for cam2web
    """

    name = "cam2web"
    description = "webcam emulator serving a camera via gphoto2"
    date = "2026-08-20"
    updated = "2026-08-20"


class Cam2WebServer(InputWebserver):
    """
    webcam emulator server - serves an MJPEG stream and stills
    """

    cameras = {
        "mock": MockCamera,
        "gphoto2": GPhoto2Camera,
    }

    @classmethod
    def get_config(cls) -> WebserverConfig:
        """
        get the configuration for this Webserver
        """
        copy_right = "(c)2026 Wolfgang Fahl"
        config = WebserverConfig(
            copy_right=copy_right,
            version=Cam2WebVersion(),
            default_port=8088,
            short_name="cam2web",
            timeout=10.0,
        )
        server_config = WebserverConfig.get(config)
        server_config.solution_class = Cam2WebSolution
        return server_config

    def __init__(self):
        """Constructs all the necessary attributes for the WebServer object."""
        InputWebserver.__init__(self, config=Cam2WebServer.get_config())
        self.camera = None

        @app.get("/still.jpg")
        def still():
            return self.still()

        @app.get("/stream.mjpg")
        def stream():
            return self.stream()

    def configure_run(self):
        """
        create the camera backend as configured via --camera
        """
        super().configure_run()
        camera_name = getattr(self.args, "camera", "gphoto2")
        camera_cls = self.cameras.get(camera_name)
        if camera_cls is None:
            raise ValueError(f"unknown camera backend: {camera_name}")
        self.camera = camera_cls()
        self.fps = getattr(self.args, "fps", 10.0)

    def still(self) -> Response:
        """
        take a picture and serve it as a JPEG
        """
        if not self.camera.claim():
            return HTMLResponse(content="camera busy", status_code=503)
        try:
            jpeg_bytes = self.camera.capture_still()
            response = Response(content=jpeg_bytes, media_type="image/jpeg")
        finally:
            self.camera.release()
        return response

    def frames(self):
        """
        generator yielding multipart MJPEG frames from the live view
        """
        try:
            delay = 1.0 / self.fps if self.fps > 0 else 0
            while True:
                frame = self.camera.preview_frame()
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    + frame
                    + b"\r\n"
                )
                if delay:
                    time.sleep(delay)
        finally:
            self.camera.release()

    def stream(self) -> Response:
        """
        serve the live view as an MJPEG stream - one client at a time
        """
        if not self.camera.claim():
            return HTMLResponse(content="camera busy", status_code=503)
        response = StreamingResponse(
            self.frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )
        return response


class Cam2WebSolution(InputWebSolution):
    """
    the cam2web solution
    """

    def __init__(self, webserver: Cam2WebServer, client: Client):
        """
        Initialize the solution
        """
        super().__init__(webserver, client)

    async def home(self):
        """
        home page showing the live view stream
        """

        def setup_home():
            ui.html('<img src="/stream.mjpg" style="max-width:100%">')

        await self.setup_content_div(setup_home)
