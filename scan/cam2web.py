"""
Created on 2026-08-20

cam2web - webcam emulator module of scan2wiki
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

import os
import queue
import sys
import threading
import time
from dataclasses import dataclass

# libgphoto2 translates its config values via gettext - keep them
# English independent of the host locale
os.environ["LANG"] = "C"
os.environ["LC_ALL"] = "C"

from basemkit.shell import Shell
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from ngwidgets.input_webserver import InputWebserver, InputWebSolution
from ngwidgets.webserver import WebserverConfig
from ngwidgets.task_runner import TaskRunner
from nicegui import Client, app, ui

from scan.version import Version


class Camera:
    """
    camera backend serving JPEG frames and stills - a single owner
    thread executes all camera commands one after the other so that
    preview, capture and configuration never race each other
    see https://github.com/WolfgangFahl/scan2wiki/issues/35
    """

    def __init__(self):
        self.commands = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    def _work(self):
        """
        the camera owner loop - executes queued commands in order
        """
        while True:
            command = self.commands.get()
            if command is None:
                break
            func, args, result, done = command
            try:
                result["value"] = func(*args)
            except Exception as ex:
                result["error"] = ex
            finally:
                done.set()

    def submit(self, func, *args, timeout: float = 60.0):
        """
        run the given camera operation on the owner thread

        Args:
            func: the operation to run
            args: arguments for the operation
            timeout (float): seconds to wait for the result

        Returns:
            the operation result
        """
        result = {}
        done = threading.Event()
        self.commands.put((func, args, result, done))
        if not done.wait(timeout):
            raise TimeoutError(f"camera command {func.__name__} timed out")
        if "error" in result:
            raise result["error"]
        return result["value"]

    def shutdown(self):
        """
        stop the owner thread
        """
        self.commands.put(None)

    def preview_frame(self) -> bytes:
        """
        get a single live view JPEG frame
        """
        return self.submit(self.do_preview_frame)

    def capture_still(self) -> bytes:
        """
        take a picture and return it as JPEG bytes
        """
        return self.submit(self.do_capture_still, timeout=90.0)

    def read_settings(self) -> dict:
        """
        read the camera settings
        """
        return self.submit(self.do_read_settings)

    def write_setting(self, key: str, value: str):
        """
        write a single camera setting
        """
        return self.submit(self.do_write_setting, key, value)

    def set_live_view(self, on: bool):
        """
        switch the live view on or off

        Args:
            on (bool): True to start the live view
        """
        return self.submit(self.do_set_live_view, on)

    def do_set_live_view(self, on: bool):
        """
        backend specific live view switch - no operation by default
        """
        return None

    def do_preview_frame(self) -> bytes:
        raise NotImplementedError

    def do_capture_still(self) -> bytes:
        raise NotImplementedError

    def do_read_settings(self) -> dict:
        return {}

    def do_write_setting(self, key: str, value: str):
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

    def do_preview_frame(self) -> bytes:
        self.frame_no += 1
        return self.render(f"mock preview {self.frame_no}")

    def do_capture_still(self) -> bytes:
        return self.render("mock still")


class GPhoto2Camera(Camera):
    """
    gphoto2 camera backend using the python-gphoto2 library
    """

    # the camera is a mechanical device - guard against churning it
    MIN_TRANSITION_INTERVAL = 1.0  # seconds between viewfinder switches
    MAX_TRANSITIONS_PER_MINUTE = 20

    def __init__(self):
        super().__init__()
        self.camera = None
        self.viewfinder_on = False
        self.transitions = []  # timestamps of viewfinder transitions

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

    def ensure_open(self):
        """
        make sure the single camera session is open
        """
        if self.camera is None:
            self.open()

    def check_transition_rate(self):
        """
        refuse to churn the camera - a viewfinder transition is a
        mechanical operation, so it is rate limited
        """
        now = time.monotonic()
        self.transitions = [t for t in self.transitions if now - t < 60]
        if len(self.transitions) >= self.MAX_TRANSITIONS_PER_MINUTE:
            raise RuntimeError(
                f"viewfinder transition rate limit of "
                f"{self.MAX_TRANSITIONS_PER_MINUTE} per minute reached"
            )
        if self.transitions:
            wait = self.MIN_TRANSITION_INTERVAL - (now - self.transitions[-1])
            if wait > 0:
                time.sleep(wait)
        self.transitions.append(time.monotonic())

    def set_viewfinder(self, on: bool):
        """
        switch the live view on or off via the camera's viewfinder
        action - this replaces closing and reopening the session

        Args:
            on (bool): True to start the live view
        """
        if self.viewfinder_on == on:
            return
        self.ensure_open()
        self.check_transition_rate()
        root = self.camera.get_config()
        node = self._cfg_node(root, "viewfinder")
        if node is not None:
            node.set_value(1 if on else 0)
            self.camera.set_config(root)
        self.viewfinder_on = on

    def recover(self):
        """
        recover from a dead camera session - close, rerun the OS
        workaround and reopen; this is the exception, not the
        normal path
        """
        try:
            self.close()
        except Exception:
            self.camera = None
        self.viewfinder_on = False
        self.os_workaround()
        self.open()

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
            # one recovery attempt - the session is rebuilt only here
            self.recover()
            result = operation()
        return result

    def do_preview_frame(self) -> bytes:
        def op() -> bytes:
            self.set_viewfinder(True)
            camera_file = self.camera.capture_preview()
            file_data = camera_file.get_data_and_size()
            return bytes(file_data)

        return self.with_retry(op)

    def do_capture_still(self) -> bytes:
        import gphoto2 as gp

        def op() -> bytes:
            was_on = self.viewfinder_on
            self.set_viewfinder(False)
            try:
                file_path = self.camera.capture(gp.GP_CAPTURE_IMAGE)
                camera_file = self.camera.file_get(
                    file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL
                )
                jpeg_bytes = bytes(camera_file.get_data_and_size())
            finally:
                if was_on:
                    self.set_viewfinder(True)
            return jpeg_bytes

        return self.with_retry(op)

    CONFIG_KEYS = [
        # imgsettings
        "iso", "whitebalance", "imageformat", "colorspace",
        # capturesettings
        "shutterspeed", "aperture", "exposurecompensation",
        "meteringmode", "focusmode", "drivemode", "autoexposuremode",
        "picturestyle", "capturetarget",
        # status
        "batterylevel", "availableshots", "shuttercounter", "cameramodel",
    ]

    def _cfg_node(self, root, name):
        try:
            return root.get_child_by_name(name)
        except Exception:
            return None

    def do_read_settings(self) -> dict:
        """
        read camera settings as {key: {"value": str, "choices": [str]}}
        - the live view keeps running, no session teardown
        """

        def op() -> dict:
            self.ensure_open()
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

    def do_write_setting(self, key: str, value: str):
        """
        set a single camera config value - the live view keeps
        running, no session teardown
        """
        def op():
            self.ensure_open()
            root = self.camera.get_config()
            node = self._cfg_node(root, key)
            if node is None:
                raise ValueError(f"unknown config key: {key}")
            node.set_value(value)
            self.camera.set_config(root)

        self.with_retry(op)

    def do_set_live_view(self, on: bool):
        """
        switch the camera's viewfinder for the live view
        """
        self.set_viewfinder(on)

    def shutdown(self):
        """
        stop the live view and close the single session
        """
        try:
            self.set_viewfinder(False)
            self.close()
        except Exception:
            self.camera = None
        super().shutdown()


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

        @ui.page("/control")
        async def control_panel(client: Client):
            return await self.page(client, Cam2WebSolution.control)

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
        self.stream_generation = 0

    def still(self) -> Response:
        """
        take a picture and serve it as a JPEG - the camera owner
        thread runs the capture between two preview frames
        """
        try:
            jpeg_bytes = self.camera.capture_still()
            response = Response(content=jpeg_bytes, media_type="image/jpeg")
        except Exception as ex:
            response = HTMLResponse(content=str(ex), status_code=503)
        return response

    def frames(self, generation: int):
        """
        generator yielding multipart MJPEG frames from the live view -
        each frame is a command on the camera owner thread, so stills
        and configuration commands interleave between frames

        Args:
            generation (int): only the newest stream keeps running
        """
        delay = 1.0 / self.fps if self.fps > 0 else 0
        try:
            while generation == self.stream_generation:
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
            if generation == self.stream_generation:
                self.camera.set_live_view(False)

    def stream(self) -> Response:
        """
        serve the live view as an MJPEG stream - a new stream ends
        the previous one so stale connections cannot pile up
        """
        self.stream_generation += 1
        response = StreamingResponse(
            self.frames(self.stream_generation),
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
        self.task_runner = TaskRunner(timeout=30.0)

    # captions for the camera config keys - key names as reported by
    # gphoto2 --list-config for the attached camera
    CONTROL_KEYS = [
        ("autoexposuremode", "Mode"),
        ("whitebalance", "WB"),
        ("meteringmode", "Metering"),
        ("iso", "ISO"),
        ("imageformat", "Quality"),
        ("exposurecompensation", "Exp"),
        ("shutterspeed", "Shutter"),
        ("aperture", "Aperture"),
        ("drivemode", "Drive"),
        ("picturestyle", "Style"),
        ("focusmode", "Focus"),
        ("capturetarget", "Target"),
    ]

    def configure_menu(self):
        """
        add the cam control entry to the menu
        """
        self.link_button("cam control", "/control", "tune", new_tab=False)

    async def home(self):
        """
        simple view - shoot, live view, stop and the image
        """

        def setup_home():
            with ui.row().classes("items-center gap-2"):
                ui.button("Shoot", icon="camera", on_click=self.shoot)
                ui.button("Live view", icon="videocam", on_click=self.live_view)
                ui.button("Stop", icon="stop", on_click=self.stop_view)
                self.status = ui.label("idle")
            self.image = ui.html(self._img(""))

        await self.setup_content_div(setup_home)

    async def control(self):
        """
        cam control view - status strip and control panel
        see https://github.com/WolfgangFahl/scan2wiki/issues/34
        """

        def setup_control():
            self._settings = {}
            self._controls = {}
            with ui.column().classes("w-full gap-3") as self.control_container:
                self._setup_lcd()
                with ui.row().classes("items-center gap-2"):
                    ui.button("Shoot", icon="camera", on_click=self.shoot)
                    ui.button(
                        "Live view", icon="videocam", on_click=self.live_view
                    )
                    ui.button("Stop", icon="stop", on_click=self.stop_view)
                    ui.button(
                        "Refresh", icon="refresh", on_click=self.refresh_settings
                    )
                    self.status = ui.label("idle")
                with ui.row().classes("w-full gap-4 items-start"):
                    self.image = ui.html(self._img(""))
                    self._setup_control_panel()
            # no automatic camera read on page load - Refresh is explicit

        await self.setup_content_div(setup_control)

    # gray LCD emulation - the camera's top display
    LCD_STYLE = (
        "background:#c8ccc0;color:#1a1a1a;font-family:monospace;"
        "padding:10px 14px;border:2px solid #8b8f85;border-radius:4px"
    )

    def _setup_lcd(self):
        """
        gray LCD panel emulating the camera top display - exposure
        line, mode, WB, metering, battery and remaining shots
        """
        with ui.column().classes("gap-1").style(self.LCD_STYLE):
            with ui.row().classes("items-center gap-6"):
                self.lcd_expo = ui.label("—  f—  ISO—").style(
                    "font-size:1.6rem;font-weight:bold"
                )
                self.lcd_shots = ui.label("[---]").style(
                    "font-size:1.6rem;font-weight:bold"
                )
            with ui.row().classes("items-center gap-4"):
                self.lcd_mode = ui.label("Mode —")
                self.lcd_wb = ui.label("WB —")
                self.lcd_metering = ui.label("Metering —")
                self.lcd_drive = ui.label("Drive —")
                self.lcd_battery = ui.label("Batt —")
                self.lcd_target = ui.label("Target —")
            self.lcd_model = ui.label("—").style("font-size:0.8rem")

    def _setup_control_panel(self):
        """
        control panel with AF/MF, destination folder, and camera
        setting dropdowns
        """
        with ui.column().classes("gap-2").style("min-width:280px"):
            ui.label("Control Panel").style("font-weight:bold")
            with ui.row().classes("items-center gap-2"):
                self.af_toggle = ui.switch("AF").tooltip("Auto / Manual focus")
                ui.label("MF")
            self.folder_input = ui.input(
                "Destination folder", value=""
            ).props("dense outlined")
            for key, caption in self.CONTROL_KEYS:
                sel = ui.select(
                    options=["—"],
                    value="—",
                    label=caption,
                    on_change=lambda e, k=key: self.apply_setting(k, e.value),
                ).props("dense outlined").classes("w-full")
                self._controls[key] = sel
            ui.button(
                "Refresh from camera",
                icon="download",
                on_click=self.refresh_settings,
            )

    def _img(self, src: str) -> str:
        style = "max-width:100%;min-height:512px;display:block"
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

    def refresh_settings(self):
        """
        read the current settings from the camera via the house
        TaskRunner so the event loop and the websocket stay alive
        """
        self.task_runner.run_blocking(self.read_settings)

    def notify(self, msg: str, msg_type: str = None):
        """
        notify from a background thread - the slot has to be entered
        explicitly, see the ngwidgets issue 1786 demo

        Args:
            msg (str): the message to show
            msg_type (str): the nicegui notification type
        """
        with self.control_container:
            if msg_type:
                ui.notify(msg, type=msg_type)
            else:
                ui.notify(msg)

    def read_settings(self):
        """
        blocking camera read - runs in a TaskRunner thread
        """
        camera = self.webserver.camera
        try:
            self._settings = camera.read_settings()
        except Exception as ex:
            self.notify(f"read settings failed: {ex}", "negative")
            self._settings = {}
        self.show_settings()

    def show_settings(self):
        """
        update the control panel selects and the status strip
        """
        with self.control_container:
            for key, sel in self._controls.items():
                info = self._settings.get(key)
                if not info:
                    sel.options = ["—"]
                    sel.value = "—"
                    sel.update()
                    continue
                options = info["choices"] or [info["value"] or "—"]
                sel.options = options
                sel.value = (
                    info["value"] if info["value"] in options else options[0]
                )
                sel.update()
            self._update_lcd()

    def _value(self, key: str) -> str:
        """
        current value of the given camera config key

        Args:
            key (str): the gphoto2 config key

        Returns:
            str: the value or an em dash if unavailable
        """
        return (self._settings.get(key) or {}).get("value") or "—"

    def _shots_text(self) -> str:
        """
        remaining shots - the camera only reports a meaningful count
        for the memory card; for internal RAM the value is a free
        space estimate and no picture count is shown

        Returns:
            str: the shots display text
        """
        target = self._value("capturetarget")
        shots = self._value("availableshots") if "card" in target.lower() else "—"
        return f"[{shots}]"

    def _lcd_value(self, key: str, prefix: str = "") -> str:
        """
        camera style rendering of a config value - non numeric
        automatics are shown as AUTO

        Args:
            key (str): the gphoto2 config key
            prefix (str): prefix for numeric values e.g. f for the aperture

        Returns:
            str: the display text
        """
        value = self._value(key)
        if value[:1].isdigit():
            text = f"{prefix}{value}"
        elif "auto" in value.lower():
            text = f"{prefix} AUTO".strip()
        else:
            text = value
        return text

    def _update_lcd(self):
        """
        update the LCD panel from the settings read from the camera
        """
        shutter = self._lcd_value("shutterspeed")
        f_stop = self._lcd_value("aperture", "f")
        iso = self._lcd_value("iso", "ISO ")
        counter = self._value("shuttercounter")
        model = self._value("cameramodel")
        self.lcd_expo.set_text(f"{shutter}  {f_stop}  {iso}")
        self.lcd_shots.set_text(self._shots_text())
        self.lcd_mode.set_text(f"Mode {self._value('autoexposuremode')}")
        self.lcd_wb.set_text(f"WB {self._value('whitebalance')}")
        self.lcd_metering.set_text(f"Metering {self._value('meteringmode')}")
        self.lcd_drive.set_text(f"Drive {self._value('drivemode')}")
        self.lcd_battery.set_text(f"Batt {self._value('batterylevel')}")
        self.lcd_target.set_text(f"Target {self._value('capturetarget')}")
        self.lcd_model.set_text(f"{model} · shutter count {counter}")

    def apply_setting(self, key: str, value: str):
        """
        write a single setting back to the camera via the TaskRunner
        """
        if value in ("—", None):
            return
        self.task_runner.run_blocking(self.write_setting, key, value)

    def write_setting(self, key: str, value: str):
        """
        blocking camera write - runs in a TaskRunner thread
        """
        camera = self.webserver.camera
        try:
            camera.write_setting(key, value)
            # dependent values change with the write - re-read them
            self._settings = camera.read_settings()
            self.notify(f"{key} = {value}")
        except Exception as ex:
            self.notify(f"{key} failed: {ex}", "negative")
        self.show_settings()
