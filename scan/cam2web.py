"""
Created on 2026-08-20

cam2web - webcam emulator module of scan2wiki
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

import asyncio
import atexit
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass

from fastapi.responses import HTMLResponse, Response, StreamingResponse
from ngwidgets.input_webserver import InputWebserver, InputWebSolution
from ngwidgets.task_runner import TaskRunner
from ngwidgets.webserver import WebserverConfig
from nicegui import Client, app, run, ui

from scan.camera import Camera, GPhoto2Camera, MockCamera
from scan.version import Version

__all__ = [
    "Camera",
    "GPhoto2Camera",
    "MockCamera",
    "Cam2WebVersion",
    "MagnifyState",
    "Cam2WebServer",
    "Cam2WebSolution",
]

logger = logging.getLogger(__name__)


@dataclass
class Cam2WebVersion(Version):
    """
    Version handling for cam2web
    """

    name = "cam2web"
    description = "webcam emulator serving a camera via gphoto2"
    date = "2026-08-20"
    updated = "2026-08-23"


class MagnifyState:
    """
    mode state machine of the magnify feature as agreed on
    https://github.com/WolfgangFahl/scan2wiki/issues/39 -
    normal shows the plain live view, select shows the draggable
    magnifying frame with the zoom view beside it, magnified fills
    the main view with the magnified area
    """

    NORMAL = "normal"
    SELECT = "select"
    MAGNIFIED = "magnified"

    def __init__(self):
        self.mode = self.NORMAL

    def set_magnify(self, on: bool):
        """
        switch the magnify feature on or off

        Args:
            on (bool): True enters selection mode, False normal mode
        """
        if on:
            self.mode = self.SELECT
        else:
            self.mode = self.NORMAL

    def click_zoom(self):
        """
        a click on the zoom view fills the main view with the
        magnified area
        """
        if self.mode == self.SELECT:
            self.mode = self.MAGNIFIED

    def click_main(self):
        """
        a click on the magnified main view returns to selection mode
        """
        if self.mode == self.MAGNIFIED:
            self.mode = self.SELECT


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
            # first kiosk page load on a Pi exceeds 10s
            # see https://github.com/WolfgangFahl/scan2wiki/issues/37
            timeout=30.0,
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
        async def still():
            return await self.still()

        @app.get("/last.jpg")
        async def last():
            return await self.last()

        @app.get("/stream.mjpg")
        async def stream():
            return await self.stream()

        @app.get("/zoom.mjpg")
        async def zoom():
            return await self.zoom()

        @app.get("/full.jpg")
        async def full():
            return await self.full()

        @app.get("/state.json")
        def state():
            return self.state()

        @app.get("/zoom/set")
        async def zoom_set(level: int = None, fx: float = None, fy: float = None):
            return await self.zoom_set(level, fx, fy)

    def state(self) -> dict:
        """
        camera and zoom state for calibration and monitoring -
        queryability per https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        camera = self.camera
        window = camera.magnify_window()
        state = {
            "rotation": camera.rotation,
            "zoom_level": camera.zoom_level,
            "camera_zoom": camera.camera_zoom,
            "window": {
                "cx": window.cx,
                "cy": window.cy,
                "width": window.width,
                "height": window.height,
            },
            "frame_size": camera.frame_size,
            "calibration": camera.calibration.model if camera.calibration else None,
            "last_error": self.last_error,
        }
        pixels = camera.commanded_pixels()
        if pixels:
            state["cam_x"], state["cam_y"] = pixels
        return state

    async def zoom_set(self, level, fx, fy):
        """
        REST control of the zoom - level 1/5/10 engages or releases
        the camera magnification, fx/fy position the magnifying frame
        center as display fractions
        """
        camera = self.camera

        def op() -> dict:
            if fx is not None and fy is not None:
                camera.set_zoom_position(fx, fy)
            if level is not None:
                camera.set_zoom(level)
                if level > 1:
                    camera.start_camera_zoom()
                elif camera.camera_zoom:
                    camera.stop_camera_zoom()
            return self.state()

        result = await run.io_bound(op)
        return result

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
        # per stream kind generation counters - a new stream of a
        # kind ends the previous one of the same kind
        self.generations = {"stream": 0, "zoom": 0}
        self.active_streams = 0
        self.last_error = None
        # frozen full frame the magnifying frame is dragged on while
        # the camera streams the magnified area - see issue 39
        self.last_full = None
        rotate = getattr(self.args, "rotate", "0")
        if rotate == "auto":
            self.camera.autorotate = True
        else:
            self.camera.rotation = int(rotate)
        # leaving the camera in live view wedges it - the next session
        # then only gets I/O in progress until the cable is replugged
        atexit.register(self.close_camera)
        # signal handlers are only available in the main thread -
        # a threaded test server runs without them
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, self.on_signal)
        app.on_shutdown(self.close_camera)

    def on_signal(self, signum, frame):
        """
        close the camera on a termination signal and exit
        """
        self.close_camera()
        sys.exit(0)

    def close_camera(self):
        """
        switch the live view off and close the camera session
        """
        camera = getattr(self, "camera", None)
        if camera:
            try:
                camera.shutdown()
            except Exception:
                pass
            self.camera = None
        self.last_still = None

    def explain_error(self, ex) -> str:
        """
        readable explanation for a camera error

        Args:
            ex: the exception

        Returns:
            str: the explanation
        """
        explain = getattr(self.camera, "explain", None)
        text = explain(ex) if explain else str(ex)
        return text

    async def still(self) -> Response:
        """
        take a picture and serve it as a JPEG - the camera owner
        thread runs the capture between two preview frames; the
        blocking wait is handed to a nicegui worker thread so that the
        event loop stays free
        """
        try:
            jpeg_bytes = await run.io_bound(self.camera.capture_still)
            self.last_error = None
            response = Response(content=jpeg_bytes, media_type="image/jpeg")
        except Exception as ex:
            self.last_error = self.explain_error(ex)
            response = HTMLResponse(content=self.last_error, status_code=503)
        return response

    async def last(self) -> Response:
        """
        serve the most recent picture from the cache
        """
        if self.last_still:
            response = Response(content=self.last_still, media_type="image/jpeg")
        else:
            response = HTMLResponse(content="no picture taken yet", status_code=404)
        return response

    async def frames(self, kind: str, generation: int):
        """
        generator yielding multipart MJPEG frames from the live view -
        each frame is a command on the camera owner thread, so stills
        and configuration commands interleave between frames

        Args:
            kind (str): "stream" for the full view, "zoom" for the
                magnifying frame view
            generation (int): only the newest stream of a kind keeps
                running
        """
        delay = 1.0 / self.fps if self.fps > 0 else 0
        if kind == "zoom":
            frame_call = self.camera.zoom_frame
        else:
            frame_call = self.camera.preview_frame
        self.active_streams += 1
        try:
            while generation == self.generations[kind]:
                try:
                    frame = await run.io_bound(frame_call)
                except Exception as ex:
                    # end the stream cleanly - the panel reports the state
                    self.last_error = self.explain_error(ex)
                    logger.error(f"{kind} stream ended: {self.last_error}")
                    break
                if frame is None:
                    # run.io_bound yields None on cancellation or
                    # shutdown - end the stream, never serve it
                    # see https://github.com/WolfgangFahl/scan2wiki/issues/40
                    break
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    + frame
                    + b"\r\n"
                )
                if delay:
                    await asyncio.sleep(delay)
        finally:
            self.active_streams -= 1
            if self.active_streams == 0:
                await run.io_bound(self.camera.set_live_view, False)

    def mjpeg_response(self, kind: str) -> Response:
        """
        serve an MJPEG stream of the given kind - a new stream ends
        the previous one of the same kind so stale connections cannot
        pile up

        Args:
            kind (str): "stream" or "zoom"

        Returns:
            Response: the streaming response
        """
        self.generations[kind] += 1
        response = StreamingResponse(
            self.frames(kind, self.generations[kind]),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )
        return response

    async def stream(self) -> Response:
        """
        serve the full live view as an MJPEG stream
        """
        response = self.mjpeg_response("stream")
        return response

    async def zoom(self) -> Response:
        """
        serve the camera magnified area as an MJPEG stream
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        response = self.mjpeg_response("zoom")
        return response

    async def full(self) -> Response:
        """
        serve the frozen full frame the magnifying frame is dragged on
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        if self.last_full:
            response = Response(content=self.last_full, media_type="image/jpeg")
        else:
            response = HTMLResponse(content="no full frame yet", status_code=404)
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
        self.magnify = MagnifyState()
        self.streaming = False
        self._dragging = False

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
            self._settings = {}
            with ui.column().classes("w-full gap-3") as self.container:
                with ui.row().classes("items-center gap-2"):
                    self.shoot_button = ui.button(
                        "Shoot", icon="camera", on_click=self.shoot
                    )
                    ui.button("Live view", icon="videocam", on_click=self.live_view)
                    ui.button("Stop", icon="stop", on_click=self.stop_view)
                    ui.button("Check camera", icon="help", on_click=self.check_camera)
                    ui.button("Reset USB", icon="usb", on_click=self.reset_camera)
                    self._setup_rotate()
                    self._setup_magnify()
                    self.status = ui.label("idle")
                self._setup_image()

        await self.setup_content_div(setup_home)

    async def control(self):
        """
        cam control view - status strip and control panel
        see https://github.com/WolfgangFahl/scan2wiki/issues/34
        """

        def setup_control():
            self._settings = {}
            self._controls = {}
            with ui.column().classes("w-full gap-3") as self.container:
                self._setup_lcd()
                with ui.row().classes("items-center gap-2"):
                    self.shoot_button = ui.button(
                        "Shoot", icon="camera", on_click=self.shoot
                    )
                    ui.button("Live view", icon="videocam", on_click=self.live_view)
                    ui.button("Stop", icon="stop", on_click=self.stop_view)
                    ui.button("Refresh", icon="refresh", on_click=self.refresh_settings)
                    self._setup_rotate()
                    self._setup_magnify()
                    self.status = ui.label("idle")
                with ui.row().classes("w-full gap-4 items-start"):
                    self._setup_image()
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
            self.folder_input = ui.input("Destination folder", value="").props(
                "dense outlined"
            )
            for key, caption in self.CONTROL_KEYS:
                sel = (
                    ui.select(
                        options=["—"],
                        value="—",
                        label=caption,
                        on_change=lambda e, k=key: self.apply_setting(k, e.value),
                    )
                    .props("dense outlined")
                    .classes("w-full")
                )
                self._controls[key] = sel
            ui.button(
                "Refresh from camera",
                icon="download",
                on_click=self.refresh_settings,
            )

    def _setup_image(self):
        """
        the picture area - the main view plus the zoom view of the
        magnify feature
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        with ui.row().classes("w-full gap-2 items-start no-wrap"):
            self.image = ui.interactive_image(
                "",
                events=["mousedown", "mousemove", "mouseup"],
                on_mouse=self.on_image_mouse,
            ).style("max-width:70%;min-height:512px")
            self.zoom_image = ui.interactive_image(
                "", events=["mousedown"], on_mouse=self.on_zoom_mouse
            ).style("max-width:28%")
            self.zoom_image.set_visibility(False)
        # magnifying frame position readout below the video
        # see https://github.com/WolfgangFahl/scan2wiki/issues/39
        self.position_label = ui.label("")

    def show_position(self):
        """
        show the magnifying frame center below the video - display
        fraction and the position actually sent to the camera
        """
        camera = self.webserver.camera
        window = camera.magnify_window()
        dx, dy = camera.view.to_display(window.cx, window.cy)
        text = f"frame {dx:.3f},{dy:.3f}"
        pixels = camera.commanded_pixels()
        if pixels:
            text += f" cam {pixels[0]},{pixels[1]}"
        self.position_label.set_text(text)

    def _setup_rotate(self):
        """
        the two rotate buttons stepping the display rotation
        see https://github.com/WolfgangFahl/scan2wiki/issues/38
        """
        ui.button(icon="rotate_left", on_click=lambda: self.rotate(-90)).tooltip(
            "rotate the view 90 degrees counterclockwise"
        )
        ui.button(icon="rotate_right", on_click=lambda: self.rotate(90)).tooltip(
            "rotate the view 90 degrees clockwise"
        )

    def _setup_magnify(self):
        """
        magnify controls - the toggle and the 5x/10x selector
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        self.magnify_switch = ui.switch(
            "Magnify", on_change=lambda e: self.set_magnify(e.value)
        ).tooltip("magnifying frame for manual focusing as in EOS Utility")
        self.level_toggle = ui.toggle(
            {5: "5x", 10: "10x"},
            value=10,
            on_change=lambda e: self.select_zoom(e.value),
        )
        self.level_toggle.set_visibility(False)

    def _bust(self, path: str) -> str:
        return f"{path}?t={time.time()}"

    def ensure_settings(self):
        """
        make sure the camera settings are known - the drive mode
        decides how long the shutter waits
        """
        if not getattr(self, "_settings", None):
            try:
                self._settings = self.webserver.camera.read_settings()
            except Exception:
                self._settings = {}

    def timer_seconds(self) -> int:
        """
        self timer delay of the current drive mode

        Returns:
            int: seconds the camera waits before the shutter fires
        """
        drivemode = self._value("drivemode") if self._settings else ""
        seconds = 0
        for token in drivemode.replace("sec", " ").split():
            if token.isdigit():
                seconds = int(token)
        return seconds

    def shoot(self):
        """
        take a still through the camera owner thread and show it -
        the button is grayed out while the camera is busy, with the
        self timer of the drive mode counted down
        """
        self.shoot_button.disable()
        self.task_runner.run_blocking(self.do_shoot)

    def check_camera(self):
        """
        report what the camera is currently able to do
        """
        self.status.set_text("checking ...")
        self.task_runner.run_blocking(self.do_check_camera)

    def reset_camera(self):
        """
        reset the USB connection to the camera
        """
        self.status.set_text("resetting ...")
        self.task_runner.run_blocking(self.do_reset_camera)

    def do_reset_camera(self):
        """
        blocking USB reset - runs in a TaskRunner thread
        """
        camera = self.webserver.camera
        if hasattr(camera, "usb_reset"):
            camera.submit(camera.usb_reset, timeout=60.0)
        status = camera.status() if hasattr(camera, "status") else "camera ready"
        with self.container:
            self.status.set_text(status)

    def do_check_camera(self):
        """
        blocking camera check - runs in a TaskRunner thread
        """
        camera = self.webserver.camera
        status = camera.status() if hasattr(camera, "status") else "camera ready"
        with self.container:
            self.status.set_text(status)

    def do_shoot(self):
        """
        blocking still capture - runs in a TaskRunner thread, the
        picture is cached by the webserver and shown from /last.jpg;
        the self timer of the drive mode is counted down so the user
        knows how long the shutter still waits
        """
        webserver = self.webserver
        try:
            self.ensure_settings()
            seconds = self.timer_seconds()
            with self.container:
                if seconds:
                    self.status.set_text(f"self timer {seconds} s - wait ...")
                else:
                    self.status.set_text("shooting ...")
            # the camera runs its self timer inside the capture
            webserver.last_still = webserver.camera.capture_still()
            webserver.last_error = None
            with self.container:
                self.image.set_source(self._bust("/last.jpg"))
                self.status.set_text("still")
        except Exception as ex:
            msg = webserver.explain_error(ex)
            with self.container:
                self.status.set_text(msg)
                ui.notify(msg, type="warning")
        finally:
            with self.container:
                self.shoot_button.enable()

    def live_view(self):
        """
        start / resume the live view stream
        """
        self.streaming = True
        self.status.set_text("live view")
        self.apply_mode()

    def stop_view(self):
        """
        stop whatever the panel currently shows - magnify is switched
        off with it
        """
        self.streaming = False
        camera = self.webserver.camera
        if camera.camera_zoom:
            self.task_runner.run_blocking(self.write_camera_zoom, False)
        self.magnify_switch.value = False
        self.image.set_source("")
        self.image.content = ""
        self.zoom_image.set_source("")
        self.status.set_text("idle")

    def rotate(self, delta: int):
        """
        step the display rotation - a view operation only, the
        magnifying frame stays anchored to the sensor area it frames;
        the running streams pick the new rotation up with their next
        frame
        see https://github.com/WolfgangFahl/scan2wiki/issues/38

        Args:
            delta (int): degrees to add, positive turns clockwise
        """
        camera = self.webserver.camera
        camera.rotate_by(delta)
        self.status.set_text(f"rotation {camera.rotation}")
        if self.magnify.mode == MagnifyState.SELECT:
            # the frozen full frame does not rotate by itself - it is
            # refreshed in one camera owner command so the zoom
            # stream never observes the released camera zoom
            self.task_runner.run_blocking(self.refresh_frozen)

    def refresh_frozen(self):
        """
        blocking refresh of the frozen full frame in selection mode
        """
        webserver = self.webserver
        camera = webserver.camera
        try:
            webserver.last_full = camera.refresh_full_frame()
        except Exception as ex:
            logger.error(f"frozen frame refresh failed: {ex}")
            self.notify(f"camera zoom failed: {ex}", "negative")
        with self.container:
            self.image.set_source(self._bust("/full.jpg"))
            self.draw_frame()
            self.show_position()

    def set_magnify(self, on: bool):
        """
        the magnify toggle - switching on enters selection mode with
        the camera's native zoom engaged as in EOS Utility, switching
        off releases the camera zoom and returns to normal mode
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Args:
            on (bool): True for selection mode, False for normal mode
        """
        camera = self.webserver.camera
        if on:
            self.status.set_text("engaging camera zoom ...")
            self.task_runner.run_blocking(self.enter_select)
        else:
            camera.set_zoom(1)
            if camera.camera_zoom:
                self.task_runner.run_blocking(self.write_camera_zoom, False)
            if self.streaming:
                self.status.set_text("live view")
            else:
                self.status.set_text("idle")
            self.magnify.set_magnify(False)
            self.apply_mode()

    def enter_select(self):
        """
        blocking transition into selection mode - a full frame is
        frozen for dragging the magnifying frame, then the camera
        takes over the magnification for the zoom view; there is no
        digital fallback - a camera that cannot magnify keeps the
        normal mode and reports why
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        webserver = self.webserver
        camera = webserver.camera
        error = None
        try:
            camera.set_zoom(int(self.level_toggle.value))
            webserver.last_full = camera.preview_frame()
            started = camera.start_camera_zoom()
        except Exception as ex:
            started = False
            error = str(ex)
        with self.container:
            if started:
                self.streaming = True
                self.magnify.set_magnify(True)
                self.status.set_text("magnify")
                self.apply_mode()
            else:
                msg = f"camera magnification not available: {error or 'no eoszoom'}"
                logger.error(msg)
                ui.notify(msg, type="negative")
                self.status.set_text(msg)
                self.magnify_switch.value = False

    def back_to_select(self):
        """
        blocking transition from the magnified view back to selection
        mode - the frozen full frame is refreshed in one camera owner
        command
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        webserver = self.webserver
        camera = webserver.camera
        try:
            webserver.last_full = camera.refresh_full_frame()
        except Exception as ex:
            logger.error(f"return to selection mode failed: {ex}")
            self.notify(f"camera zoom failed: {ex}", "negative")
        with self.container:
            self.magnify.click_main()
            self.apply_mode()

    def write_camera_zoom(self, on: bool):
        """
        blocking camera magnification switch - runs in a TaskRunner
        thread

        Args:
            on (bool): True to engage the camera magnification
        """
        camera = self.webserver.camera
        try:
            if on:
                camera.start_camera_zoom()
            else:
                camera.stop_camera_zoom()
        except Exception as ex:
            logger.error(f"camera zoom switch failed: {ex}")
            self.notify(f"camera zoom failed: {ex}", "negative")

    def select_zoom(self, level: int):
        """
        apply the selected magnification to the zoom view
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Args:
            level (int): 5 or 10
        """
        if self.magnify.mode != MagnifyState.NORMAL:
            self.webserver.camera.set_zoom(int(level))
            if self.magnify.mode == MagnifyState.SELECT:
                self.draw_frame()

    def apply_mode(self):
        """
        render the current magnify mode - stream sources, zoom view
        visibility and the magnifying frame overlay
        """
        mode = self.magnify.mode
        self.level_toggle.set_visibility(mode != MagnifyState.NORMAL)
        self.zoom_image.set_visibility(mode == MagnifyState.SELECT)
        if mode == MagnifyState.SELECT:
            # the camera streams the magnified area - the main view
            # freezes on the last full frame for dragging the frame
            self.image.set_source(self._bust("/full.jpg"))
            self.zoom_image.set_source(self._bust("/zoom.mjpg"))
            self.draw_frame()
        elif mode == MagnifyState.MAGNIFIED:
            self.zoom_image.set_source("")
            self.image.content = ""
            self.image.set_source(self._bust("/zoom.mjpg"))
        else:
            self.zoom_image.set_source("")
            self.image.content = ""
            if self.streaming:
                self.image.set_source(self._bust("/stream.mjpg"))

    def draw_frame(self):
        """
        draw the magnifying frame on the main view
        """
        camera = self.webserver.camera
        width, height = camera.frame_size or (768, 512)
        x0, y0, fw, fh = camera.display_box()
        content = (
            f'<rect x="{x0 * width:.0f}" y="{y0 * height:.0f}" '
            f'width="{fw * width:.0f}" height="{fh * height:.0f}" '
            'fill="none" stroke="red" stroke-width="4" />'
        )
        self.image.content = content

    def in_frame(self, fx: float, fy: float) -> bool:
        """
        whether the given display point lies inside the magnifying
        frame

        Args:
            fx (float): horizontal fraction of the display
            fy (float): vertical fraction of the display

        Returns:
            bool: True if the point is inside the frame
        """
        x0, y0, fw, fh = self.webserver.camera.display_box()
        inside = x0 <= fx <= x0 + fw and y0 <= fy <= y0 + fh
        return inside

    def on_image_mouse(self, e):
        """
        magnify interaction on the main view - drag the frame in
        selection mode, click to leave the magnified view

        Args:
            e: the nicegui mouse event with image coordinates
        """
        mode = self.magnify.mode
        if mode == MagnifyState.MAGNIFIED:
            if e.type == "mousedown":
                self.task_runner.run_blocking(self.back_to_select)
        elif mode == MagnifyState.SELECT:
            self.drag_frame(e)

    def drag_frame(self, e):
        """
        drag the magnifying frame - grabbing starts inside the frame,
        the zoom view follows live

        Args:
            e: the nicegui mouse event with image coordinates
        """
        camera = self.webserver.camera
        size = camera.frame_size
        if not size:
            return
        fx = e.image_x / size[0]
        fy = e.image_y / size[1]
        if e.type == "mousedown":
            self._dragging = self.in_frame(fx, fy)
        elif e.type == "mouseup":
            self._dragging = False
        if self._dragging and e.type in ("mousedown", "mousemove"):
            camera.set_zoom_position(fx, fy)
            self.draw_frame()
            self.show_position()

    def on_zoom_mouse(self, e):
        """
        a click on the zoom view fills the main view with the
        magnified area

        Args:
            e: the nicegui mouse event
        """
        if e.type == "mousedown" and self.magnify.mode == MagnifyState.SELECT:
            # the camera zoom is already engaged - the magnified
            # stream just fills the main view
            self.magnify.click_zoom()
            self.apply_mode()

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
        with self.container:
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
        with self.container:
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
