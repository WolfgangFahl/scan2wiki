"""
Created on 2026-08-20

cam2web - webcam emulator module of scan2wiki
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

import sys
import threading
import time
from dataclasses import dataclass

from basemkit.shell import Shell
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
        self.stop_stream = threading.Event()

    def claim(self, wait: float = 0.0) -> bool:
        """
        claim the camera for a single client - if a stream holds
        the lock, signal it to stop and wait up to `wait` seconds

        Args:
            wait (float): seconds to wait for the current holder to release

        Returns:
            bool: True if the camera was claimed
        """
        self.stop_stream.set()
        if wait > 0:
            claimed = self.lock.acquire(blocking=True, timeout=wait)
        else:
            claimed = self.lock.acquire(blocking=False)
        self.stop_stream.clear()
        return claimed

    def release(self):
        """
        release the camera
        """
        if self.lock.locked():
            try:
                self.lock.release()
            except RuntimeError:
                pass

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

    shell = Shell()
    daemons = {
        "darwin": "ptpcamerad",
        "linux": "gvfsd-gphoto2",
    }

    @classmethod
    def os_workaround(cls):
        """
        OS daemons claim the USB device and block gphoto2 -
        ptpcamerad on macOS, gvfsd-gphoto2 on Linux - kill them
        and wait until they are gone before returning
        """
        daemon = cls.daemons.get(sys.platform)
        if not daemon:
            return
        cls.shell.run(f"killall -9 {daemon}", debug=False)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            r = cls.shell.run(f"pgrep -x {daemon}", debug=False)
            if r.returncode != 0:
                return
            time.sleep(0.05)

    def open(self):
        """
        initialize the gphoto2 camera connection - retry on
        transient USB claim races
        """
        import gphoto2 as gp

        last_err = None
        for _ in range(3):
            self.os_workaround()
            try:
                self.camera = gp.Camera()
                self.camera.init()
                return
            except gp.GPhoto2Error as ex:
                last_err = ex
                self.camera = None
                time.sleep(0.3)
        raise last_err

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
            if self.camera is None:
                self.open()
            self.mode = mode

    def recover(self):
        """
        recover from a dead camera connection - close, rerun
        the OS workaround and reopen
        """
        mode = self.mode
        try:
            self.close()
        except Exception:
            self.camera = None
            self.mode = None
        self.os_workaround()
        self.open()
        self.mode = mode

    def with_retry(self, operation):
        """
        run the given camera operation, recovering once on GPhoto2Error;
        on second failure release the claim and propagate the error

        Args:
            operation: callable performing the camera operation

        Returns:
            bytes: JPEG image data
        """
        import gphoto2 as gp

        try:
            result = operation()
        except gp.GPhoto2Error:
            try:
                self.recover()
                result = operation()
            except Exception:
                self.release()
                raise
        return result

    def preview_frame(self) -> bytes:
        def op() -> bytes:
            self.switch_mode("preview")
            camera_file = self.camera.capture_preview()
            file_data = camera_file.get_data_and_size()
            return bytes(file_data)

        return self.with_retry(op)

    def capture_still(self) -> bytes:
        import gphoto2 as gp

        def op() -> bytes:
            self.switch_mode("still")
            file_path = self.camera.capture(gp.GP_CAPTURE_IMAGE)
            camera_file = self.camera.file_get(
                file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL
            )
            file_data = camera_file.get_data_and_size()
            return bytes(file_data)

        return self.with_retry(op)

    CONFIG_KEYS = [
        "iso", "whitebalance", "imageformat", "imagequality",
        "shutterspeed", "aperture", "exposurecompensation",
        "meteringmode", "focusmode", "capturetarget", "batterylevel",
    ]

    def _cfg_node(self, root, name):
        try:
            return root.get_child_by_name(name)
        except Exception:
            return None

    def read_settings(self) -> dict:
        """
        read camera settings as {key: {"value": str, "choices": [str]}}
        - runs under the shared lock, must be called after claim
        """
        import gphoto2 as gp

        def op() -> dict:
            self.switch_mode("still")
            root = self.camera.get_config()
            out = {}
            for key in self.CONFIG_KEYS:
                node = self._cfg_node(root, key)
                if node is None:
                    continue
                try:
                    value = str(node.get_value())
                except Exception:
                    value = ""
                choices = []
                try:
                    choices = [str(c) for c in node.get_choices()]
                except Exception:
                    pass
                out[key] = {"value": value, "choices": choices}
            return out

        return self.with_retry(op)

    def write_setting(self, key: str, value: str):
        """
        set a single camera config value
        """
        def op():
            self.switch_mode("still")
            root = self.camera.get_config()
            node = self._cfg_node(root, key)
            if node is None:
                raise ValueError(f"unknown config key: {key}")
            node.set_value(value)
            self.camera.set_config(root)

        self.with_retry(op)

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

        @ui.page("/")
        async def shooting_panel(client: Client):
            return await self.page(client, Cam2WebSolution.home)

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
        take a picture and serve it as a JPEG - stops any active
        stream and waits up to 5 s for the lock to free up
        """
        if not self.camera.claim(wait=5.0):
            return HTMLResponse(content="camera busy", status_code=503)
        try:
            jpeg_bytes = self.camera.capture_still()
            response = Response(content=jpeg_bytes, media_type="image/jpeg")
        finally:
            self.camera.release()
        return response

    def frames(self):
        """
        generator yielding multipart MJPEG frames from the live view -
        exits cleanly when Camera.stop_stream is signalled
        """
        try:
            delay = 1.0 / self.fps if self.fps > 0 else 0
            while not self.camera.stop_stream.is_set():
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

    CONTROL_KEYS = [
        ("whitebalance", "WB"),
        ("meteringmode", "Metering"),
        ("iso", "ISO"),
        ("imagequality", "Quality"),
        ("exposurecompensation", "Exp"),
        ("shutterspeed", "Shutter"),
        ("aperture", "Aperture"),
    ]

    async def home(self):
        """
        remote shooting panel - LCD status strip, control panel,
        live view window and shutter - see
        https://github.com/WolfgangFahl/scan2wiki/issues/34
        """

        def setup_home():
            self._settings = {}
            self._controls = {}
            with ui.column().classes("w-full gap-3"):
                self._setup_lcd_strip()
                with ui.row().classes("w-full gap-4 items-start"):
                    self._setup_live_view()
                    self._setup_control_panel()

        await self.setup_content_div(setup_home)

    def _setup_lcd_strip(self):
        """
        LCD-styled status strip with the shutter and view controls -
        always visible at the top of the panel
        """
        with ui.row().classes(
            "w-full items-center gap-4 rounded"
        ).style(
            "background:#111;color:#ffd700;"
            "font-family:monospace;padding:8px 12px"
        ):
            ui.button(icon="camera", on_click=self.shoot).props(
                "round color=red size=lg"
            ).tooltip("Shoot")
            ui.button(icon="videocam", on_click=self.live_view).props(
                "flat color=yellow"
            ).tooltip("Live view")
            ui.button(icon="stop", on_click=self.stop_view).props(
                "flat color=yellow"
            ).tooltip("Stop")
            ui.separator().props("vertical")
            self.lcd_model = ui.label("Camera: —")
            self.lcd_battery = ui.label("Battery: —")
            self.lcd_drive = ui.label("Drive: —")
            self.lcd_shots = ui.label("Shots: —")
            self.lcd_expo = ui.label("— · f— · ISO—")
            self.status = ui.label("idle").style("margin-left:auto")
            ui.button(icon="refresh", on_click=self.refresh_settings).props(
                "flat color=yellow"
            ).tooltip("Refresh from camera")

    def _setup_live_view(self):
        """
        live view / still window
        """
        with ui.column().classes("gap-2").style("min-width:520px"):
            self.image = ui.html(self._img(""))

    def _setup_control_panel(self):
        """
        control panel with AF/MF, destination folder, and camera
        setting dropdowns
        """
        with ui.column().classes("gap-2").style(
            "min-width:280px;background:#222;color:#eee;padding:12px;border-radius:6px"
        ):
            ui.label("Control Panel").style("font-weight:bold")
            with ui.row().classes("items-center gap-2"):
                self.af_toggle = ui.switch("AF").tooltip("Auto / Manual focus")
                ui.label("MF")
            self.folder_input = ui.input(
                "Destination folder", value=""
            ).props("dense outlined dark")
            for key, caption in self.CONTROL_KEYS:
                sel = ui.select(
                    options=["—"],
                    value="—",
                    label=caption,
                    on_change=lambda e, k=key: self.apply_setting(k, e.value),
                ).props("dense outlined dark").classes("w-full")
                self._controls[key] = sel
            ui.button(
                "Refresh from camera",
                icon="download",
                on_click=self.refresh_settings,
            )

    def _img(self, src: str) -> str:
        style = "max-width:100%;min-height:512px;background:#222;display:block"
        return f'<img src="{src}" style="{style}">' if src else (
            f'<div style="{style}"></div>'
        )

    def _bust(self, path: str) -> str:
        return f"{path}?t={time.time()}"

    def shoot(self):
        """
        take a still - the server side stops any active stream and
        serves the JPEG, the browser then shows it in place
        """
        self.status.set_text("shooting ...")
        self.image.content = self._img(self._bust("/still.jpg"))
        self.status.set_text("still")

    def live_view(self):
        """
        start / resume the live view stream
        """
        self.image.content = self._img(self._bust("/stream.mjpg"))
        self.status.set_text("live view")

    def stop_view(self):
        """
        stop whatever the panel currently shows
        """
        self.image.content = self._img("")
        self.status.set_text("idle")

    async def refresh_settings(self):
        """
        read the current settings from the camera and update the
        control panel and LCD status strip
        """
        camera = self.webserver.camera
        if not camera.claim(wait=5.0):
            ui.notify("camera busy", type="warning")
            return
        try:
            self._settings = camera.read_settings()
        except Exception as ex:
            ui.notify(f"read settings failed: {ex}", type="negative")
            self._settings = {}
        finally:
            camera.release()
        for key, sel in self._controls.items():
            info = self._settings.get(key)
            if not info:
                sel.options = ["—"]
                sel.value = "—"
                sel.update()
                continue
            options = info["choices"] or [info["value"] or "—"]
            sel.options = options
            sel.value = info["value"] if info["value"] in options else options[0]
            sel.update()
        self._update_lcd()

    def _update_lcd(self):
        s = self._settings
        battery = (s.get("batterylevel") or {}).get("value") or "—"
        shutter = (s.get("shutterspeed") or {}).get("value") or "—"
        aperture = (s.get("aperture") or {}).get("value") or "—"
        iso = (s.get("iso") or {}).get("value") or "—"
        self.lcd_battery.set_text(f"Battery: {battery}")
        self.lcd_drive.set_text("Drive: single")
        self.lcd_shots.set_text("Shots: —")
        self.lcd_model.set_text("Camera: Canon EOS 1000D")
        self.lcd_expo.set_text(f"{shutter} · f{aperture} · ISO{iso}")

    async def apply_setting(self, key: str, value: str):
        """
        write a single setting back to the camera
        """
        if value in ("—", None):
            return
        camera = self.webserver.camera
        if not camera.claim(wait=5.0):
            ui.notify("camera busy", type="warning")
            return
        try:
            camera.write_setting(key, value)
            ui.notify(f"{key} = {value}")
        except Exception as ex:
            ui.notify(f"{key} failed: {ex}", type="negative")
        finally:
            camera.release()
        self._update_lcd()
