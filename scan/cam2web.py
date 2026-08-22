"""
Created on 2026-08-20

cam2web - webcam emulator module of scan2wiki
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

import asyncio
import atexit
import logging
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass
from io import BytesIO

# libgphoto2 translates its config values via gettext - keep them
# English independent of the host locale
os.environ["LANG"] = "C"
os.environ["LC_ALL"] = "C"

from basemkit.shell import Shell
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from ngwidgets.input_webserver import InputWebserver, InputWebSolution
from ngwidgets.task_runner import TaskRunner
from ngwidgets.webserver import WebserverConfig
from nicegui import Client, app, run, ui
from PIL import Image, ImageOps

from scan.version import Version

logger = logging.getLogger(__name__)


class Camera:
    """
    camera backend serving JPEG frames and stills - a single owner
    thread executes all camera commands one after the other so that
    preview, capture and configuration never race each other
    see https://github.com/WolfgangFahl/scan2wiki/issues/35
    """

    # magnifying frame zoom levels as in EOS Utility
    # see https://github.com/WolfgangFahl/scan2wiki/issues/39
    ZOOM_LEVELS = [1, 5, 10]

    def __init__(self):
        self.zoom_level = 1
        # magnifying frame center as fractions of the frame
        self.zoom_fx = 0.5
        self.zoom_fy = 0.5
        # clockwise display rotation in degrees - see issue 38
        self.rotation = 0
        # transpose stills per their EXIF orientation tag
        self.autorotate = False
        # True while the camera itself performs the magnification
        self.camera_zoom = False
        # True while a zoom level or position change still has to be
        # written to the magnifying camera
        self.zoom_dirty = False
        # (width, height) of the last full preview frame
        self.frame_size = None
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
        get a single full live view JPEG frame with the display
        rotation applied
        """
        return self.submit(self.do_full_preview)

    def zoom_frame(self) -> bytes:
        """
        get the magnifying frame area of the live view enlarged to
        the full frame size
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        return self.submit(self.do_zoom_preview)

    def capture_still(self) -> bytes:
        """
        take a picture and return it as JPEG bytes - autorotate
        transposes per the EXIF orientation tag, the display rotation
        is applied on top
        see https://github.com/WolfgangFahl/scan2wiki/issues/38
        """
        jpeg_bytes = self.submit(self.do_capture_still, timeout=90.0)
        if self.autorotate:
            jpeg_bytes = self.exif_transpose(jpeg_bytes)
        jpeg_bytes = self.apply_rotation(jpeg_bytes)
        return jpeg_bytes

    def rotate_by(self, delta: int):
        """
        step the display rotation by the given signed degrees

        Args:
            delta (int): degrees to add, positive turns clockwise
        """
        self.rotation = (self.rotation + delta) % 360

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

    def set_zoom(self, level: int):
        """
        set the zoom view magnification - while the camera magnifies
        the new level is pushed to the camera with the next zoom frame
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Args:
            level (int): 1, 5 or 10 as in EOS Utility
        """
        if level not in self.ZOOM_LEVELS:
            raise ValueError(f"zoom level {level} not in {self.ZOOM_LEVELS}")
        self.zoom_level = level
        if self.camera_zoom:
            self.zoom_dirty = True

    def set_zoom_position(self, fx: float, fy: float):
        """
        position the magnifying frame center on the full frame -
        while the camera magnifies the new position is pushed to the
        camera with the next zoom frame

        Args:
            fx (float): horizontal center as fraction of the full frame
            fy (float): vertical center as fraction of the full frame
        """
        self.zoom_fx = min(max(fx, 0.0), 1.0)
        self.zoom_fy = min(max(fy, 0.0), 1.0)
        if self.camera_zoom:
            self.zoom_dirty = True

    def crop_fractions(self) -> tuple:
        """
        the magnifying frame as fractions of the full frame, clamped
        to its borders

        Returns:
            tuple: (x0, y0, width, height) fractions
        """
        width = 1.0 / self.zoom_level
        height = 1.0 / self.zoom_level
        x0 = min(max(self.zoom_fx - width / 2, 0.0), 1.0 - width)
        y0 = min(max(self.zoom_fy - height / 2, 0.0), 1.0 - height)
        return x0, y0, width, height

    def do_full_preview(self) -> bytes:
        """
        full preview frame with the display rotation applied - the
        frame size is measured on the rotated frame so that frame
        coordinates match what the user sees
        """
        frame = self.apply_rotation(self.do_preview_frame())
        self.measure_frame(frame)
        return frame

    def do_zoom_preview(self) -> bytes:
        """
        the zoom view frame - the camera itself magnifies via its
        native zoom as in EOS Utility, so the preview already is the
        framed area at native resolution; there is no digital zoom
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        if not self.camera_zoom:
            raise RuntimeError(
                "camera magnification not engaged - no digital zoom is served"
            )
        if self.zoom_dirty:
            self.do_apply_camera_zoom()
            self.zoom_dirty = False
        frame = self.apply_rotation(self.do_preview_frame())
        return frame

    def start_camera_zoom(self) -> bool:
        """
        engage the camera's own magnification for the zoom view -
        the base camera has none, so magnify is unavailable
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Returns:
            bool: True if the camera magnifies itself
        """
        started = False
        return started

    def do_apply_camera_zoom(self):
        """
        push the current zoom level and magnifying frame position to
        the magnifying camera - no operation by default
        """
        return None

    def stop_camera_zoom(self):
        """
        release the camera's own magnification
        """
        self.camera_zoom = False

    def measure_frame(self, jpeg_bytes: bytes):
        """
        record the pixel size of the given full frame - a frame the
        image library cannot parse leaves the size unknown
        """
        try:
            image = Image.open(BytesIO(jpeg_bytes))
            self.frame_size = image.size
        except Exception:
            self.frame_size = None

    def to_jpeg(self, image: Image.Image) -> bytes:
        """
        encode the given image as JPEG bytes

        Args:
            image: the image to encode

        Returns:
            bytes: the JPEG data
        """
        buffer = BytesIO()
        image.convert("RGB").save(buffer, "JPEG")
        jpeg_bytes = buffer.getvalue()
        return jpeg_bytes

    def apply_rotation(self, jpeg_bytes: bytes) -> bytes:
        """
        rotate the given JPEG clockwise by the display rotation
        see https://github.com/WolfgangFahl/scan2wiki/issues/38

        Args:
            jpeg_bytes (bytes): the image to rotate

        Returns:
            bytes: the rotated JPEG
        """
        rotated_bytes = jpeg_bytes
        if self.rotation % 360 != 0:
            image = Image.open(BytesIO(jpeg_bytes))
            rotated = image.rotate(-self.rotation, expand=True)
            rotated_bytes = self.to_jpeg(rotated)
        return rotated_bytes

    def exif_transpose(self, jpeg_bytes: bytes) -> bytes:
        """
        transpose the given JPEG per its EXIF orientation tag - a
        frame without a tag is returned unchanged
        see https://github.com/WolfgangFahl/scan2wiki/issues/38

        Args:
            jpeg_bytes (bytes): the image to transpose

        Returns:
            bytes: the transposed JPEG
        """
        transposed_bytes = jpeg_bytes
        image = Image.open(BytesIO(jpeg_bytes))
        transposed = ImageOps.exif_transpose(image)
        if transposed is not image:
            transposed_bytes = self.to_jpeg(transposed)
        return transposed_bytes

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
        if self.camera_zoom:
            text = (
                f"mock zoom {self.zoom_level}x "
                f"{self.zoom_fx:.2f},{self.zoom_fy:.2f} {self.frame_no}"
            )
        else:
            text = f"mock preview {self.frame_no}"
        return self.render(text)

    def do_capture_still(self) -> bytes:
        return self.render("mock still")

    def start_camera_zoom(self) -> bool:
        """
        the mock stands in for an EOS camera whose native zoom serves
        the framed area - engaging always succeeds
        """
        self.camera_zoom = True
        return True


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

    def usb_reset(self):
        """
        reset the USB connection - the only remote remedy for a
        camera that reports I/O in progress; a mechanical reset by
        replugging the cable is not always possible
        """
        try:
            self.close()
        except Exception:
            self.camera = None
        self.os_workaround()
        self.shell.run("gphoto2 --reset", debug=False)
        self.power_cycle()
        time.sleep(1.0)

    def power_cycle(self):
        """
        power cycle the camera's USB port with uhubctl where the hub
        supports per port power switching - this is a replug without
        hands at the cable
        """
        r = self.shell.run("which uhubctl", debug=False)
        if r.returncode != 0:
            return
        # find the hub and port the camera is connected to
        r = self.shell.run("sudo -n uhubctl", debug=False)
        hub = None
        for line in (r.stdout or "").splitlines():
            if line.startswith("Current status for hub"):
                hub = line.split()[4]
            if "04a9:" in line and hub:
                port = line.split()[1].rstrip(":")
                self.shell.run(
                    f"sudo -n uhubctl -l {hub} -p {port} -a cycle --delay 3",
                    debug=False,
                )
                time.sleep(4.0)
                break
        self.viewfinder_on = False

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

    # gphoto2 error codes that a session rebuild can cure - measured
    # on the EOS 1000D: -53 could not claim the USB device is caused
    # by the OS daemon, -7 and -1 by a stale session. -110 I/O in
    # progress and the Canon 2019 release failure are camera states
    # that a rebuild does not cure, so they are reported as is
    RECOVERABLE = (-53, -7, -1, -52)

    def with_retry(self, operation):
        """
        run the given camera operation, rebuilding the session once
        for errors a rebuild can cure

        Args:
            operation: callable performing the camera operation

        Returns:
            the operation result
        """
        import gphoto2 as gp

        try:
            result = operation()
        except gp.GPhoto2Error as ex:
            if ex.code not in self.RECOVERABLE:
                raise
            # one recovery attempt - the session is rebuilt only here
            self.recover()
            result = operation()
        return result

    def status(self) -> str:
        """
        one line camera status for the user interface

        Returns:
            str: what the camera is currently able to do
        """
        import gphoto2 as gp

        try:
            self.submit(self.do_status, timeout=20.0)
            text = "camera ready"
        except gp.GPhoto2Error as ex:
            text = self.explain(ex)
        except Exception as ex:
            text = str(ex)
        return text

    def do_status(self):
        self.ensure_open()
        self.camera.get_config()

    @classmethod
    def explain(cls, ex) -> str:
        """
        turn a gphoto2 error into an instruction the user can act on

        Args:
            ex: the GPhoto2Error

        Returns:
            str: the explanation
        """
        explanations = {
            -110: "camera busy - unplug and replug the USB cable",
            -53: "another program holds the camera",
            -10: "camera not responding - unplug and replug the USB cable",
        }
        text = explanations.get(getattr(ex, "code", None), str(ex))
        if "2019" in str(ex):
            text = "camera refuses to release - check lens switch on MF, mode dial and lens cap"
        return text

    def do_preview_frame(self) -> bytes:
        def op() -> bytes:
            self.ensure_open()
            self.set_viewfinder(True)
            camera_file = self.camera.capture_preview()
            file_data = camera_file.get_data_and_size()
            return bytes(file_data)

        return self.with_retry(op)

    def do_capture_still(self) -> bytes:
        import gphoto2 as gp

        def op() -> bytes:
            self.ensure_open()
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
        "iso",
        "whitebalance",
        "imageformat",
        "colorspace",
        # capturesettings
        "shutterspeed",
        "aperture",
        "exposurecompensation",
        "meteringmode",
        "focusmode",
        "drivemode",
        "autoexposuremode",
        "picturestyle",
        "capturetarget",
        # status
        "batterylevel",
        "availableshots",
        "shuttercounter",
        "cameramodel",
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

    # coordinate space of the eoszoomposition config entry -
    # libgphoto2 passes the raw values to the camera
    ZOOM_POSITION_SIZE = (8192, 8192)

    def unrotate_fraction(self, fx: float, fy: float) -> tuple:
        """
        map display fractions back to sensor fractions - the user
        positions the magnifying frame on the rotated view while the
        camera addresses the unrotated sensor

        Args:
            fx (float): horizontal fraction of the rotated view
            fy (float): vertical fraction of the rotated view

        Returns:
            tuple: (fx, fy) fractions on the sensor
        """
        rotation = self.rotation % 360
        if rotation == 90:
            sensor = (fy, 1.0 - fx)
        elif rotation == 180:
            sensor = (1.0 - fx, 1.0 - fy)
        elif rotation == 270:
            sensor = (1.0 - fy, fx)
        else:
            sensor = (fx, fy)
        return sensor

    def start_camera_zoom(self) -> bool:
        """
        magnify on the camera via the eoszoom config entry with the
        magnifying frame position sent along via eoszoomposition
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Returns:
            bool: True if the camera magnifies itself
        """
        started = self.submit(self.do_start_camera_zoom)
        return started

    def write_zoom_config(self, root) -> bool:
        """
        write the zoom level to eoszoom and the magnifying frame
        position to eoszoomposition on the given config root

        Args:
            root: the gphoto2 config root

        Returns:
            bool: True if the camera supports eoszoom
        """
        node = self._cfg_node(root, "eoszoom")
        supported = node is not None
        if supported:
            node.set_value(str(self.zoom_level))
            position = self._cfg_node(root, "eoszoomposition")
            if position is not None:
                sx, sy = self.unrotate_fraction(self.zoom_fx, self.zoom_fy)
                x = int(sx * self.ZOOM_POSITION_SIZE[0])
                y = int(sy * self.ZOOM_POSITION_SIZE[1])
                position.set_value(f"{x},{y}")
            self.camera.set_config(root)
        return supported

    def do_start_camera_zoom(self) -> bool:
        """
        camera owner thread part of start_camera_zoom
        """

        def op() -> bool:
            self.ensure_open()
            root = self.camera.get_config()
            return self.write_zoom_config(root)

        started = self.with_retry(op)
        self.camera_zoom = started
        return started

    def do_apply_camera_zoom(self):
        """
        push a pending zoom level or magnifying frame position change
        to the camera - runs on the owner thread between zoom frames
        """

        def op():
            self.ensure_open()
            root = self.camera.get_config()
            self.write_zoom_config(root)

        self.with_retry(op)

    def stop_camera_zoom(self):
        """
        release the camera's own magnification
        """
        self.submit(self.do_stop_camera_zoom)

    def do_stop_camera_zoom(self):
        """
        camera owner thread part of stop_camera_zoom
        """

        def op():
            self.ensure_open()
            root = self.camera.get_config()
            node = self._cfg_node(root, "eoszoom")
            if node is not None:
                node.set_value("1")
                self.camera.set_config(root)

        self.with_retry(op)
        self.camera_zoom = False

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
    updated = "2026-08-22"


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
        step the display rotation - the running streams pick the new
        rotation up with their next frame
        see https://github.com/WolfgangFahl/scan2wiki/issues/38

        Args:
            delta (int): degrees to add, positive turns clockwise
        """
        camera = self.webserver.camera
        camera.rotate_by(delta)
        self.status.set_text(f"rotation {camera.rotation}")

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
        mode - the frozen full frame is refreshed between releasing
        and re-engaging the camera zoom
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        webserver = self.webserver
        camera = webserver.camera
        try:
            camera.stop_camera_zoom()
            webserver.last_full = camera.preview_frame()
            camera.start_camera_zoom()
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
        x0, y0, fw, fh = camera.crop_fractions()
        content = (
            f'<rect x="{x0 * width:.0f}" y="{y0 * height:.0f}" '
            f'width="{fw * width:.0f}" height="{fh * height:.0f}" '
            'fill="none" stroke="red" stroke-width="4" />'
        )
        self.image.content = content

    def in_frame(self, fx: float, fy: float) -> bool:
        """
        whether the given fractional point lies inside the magnifying
        frame

        Args:
            fx (float): horizontal fraction of the full frame
            fy (float): vertical fraction of the full frame

        Returns:
            bool: True if the point is inside the frame
        """
        x0, y0, fw, fh = self.webserver.camera.crop_fractions()
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
