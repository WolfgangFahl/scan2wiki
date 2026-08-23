"""
Created on 2026-08-20

camera - camera backends of the cam2web module
see https://github.com/WolfgangFahl/scan2wiki/issues/33

All magnify state lives on the standard grid of scan.geometry - the
unrotated sensor unit square. Display rotation is a pure view
transform, so the framed sensor area stays put when the view rotates.

@author: wf
"""

import logging
import os
import queue
import sys
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# libgphoto2 translates its config values via gettext - keep them
# English independent of the host locale
os.environ["LANG"] = "C"
os.environ["LC_ALL"] = "C"

from basemkit.shell import Shell
from basemkit.yamlable import lod_storable
from PIL import Image, ImageOps

from scan.geometry import Axis, Calibration, Grid, Rotation, Window

logger = logging.getLogger(__name__)


@lod_storable
class CameraCalibration:
    """
    measured per camera model magnify constants - all values come
    from a ruler scene calibration sweep on the live camera, never
    from data sheets; see
    https://github.com/WolfgangFahl/scan2wiki/issues/41
    """

    model: str = ""
    # the level the camera magnifies natively; higher levels are
    # served as digital enlargement of the native window as in
    # EOS Utility
    native_zoom_level: int = 5
    # pixel size of the served zoom frame
    zoom_raster: List[int] = None
    # native window size as fractions of the full view
    window_fraction: List[float] = None
    # per axis eoszoomposition response as [scale, offset, cmd_max]:
    # command = scale * top_left_fraction + offset, honored up to
    # cmd_max - see geometry.Axis
    x_axis: List[float] = None
    y_axis: List[float] = None

    @property
    def geometry(self) -> Calibration:
        """
        the measured constants as a geometry Calibration
        """
        width, height = self.window_fraction
        calibration = Calibration(
            x_axis=Axis(*self.x_axis),
            y_axis=Axis(*self.y_axis),
            window_width=width,
            window_height=height,
        )
        return calibration


@lod_storable
class CameraCalibrations:
    """
    the calibrated camera models from cameras.yaml
    """

    cameras: Dict[str, CameraCalibration] = None

    @classmethod
    def get_instance(cls) -> "CameraCalibrations":
        """
        load the calibrations shipped with scan2wiki
        """
        yaml_path = Path(__file__).parent.parent / "scan2wiki_examples" / "cameras.yaml"
        instance = cls.load_from_yaml_file(str(yaml_path))
        return instance


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

    # full-size image coordinate space of the camera's zoom position
    # entry - None for backends without their own magnification
    ZOOM_POSITION_SIZE: Optional[Tuple[int, int]] = None

    def __init__(self):
        self.zoom_level = 1
        # display rotation as a view transform - see issue 38
        self.view = Rotation()
        # magnifying frame on the standard grid - see issue 39
        self.window = Window()
        # transpose stills per their EXIF orientation tag
        self.autorotate = False
        # True while the camera itself performs the magnification
        self.camera_zoom = False
        # True while a zoom level or position change still has to be
        # written to the magnifying camera
        self.zoom_dirty = False
        # the zoom level last written to the camera - the camera's
        # own readback always reports 0, so the level written is the
        # only truth; reset when the served frames prove it wrong
        self.applied_level = 1
        # True once a served frame has the calibrated zoom raster -
        # the camera ignores position writes while still engaging,
        # so positions are only sent after this confirmation
        self.zoom_confirmed = False
        # (width, height) of the last full preview frame
        self.frame_size = None
        # measured per model magnify constants, resolved on open
        self.calibration: Optional[CameraCalibration] = None
        self.commands = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    @property
    def rotation(self) -> int:
        """
        clockwise display rotation in degrees
        """
        return self.view.degrees

    @rotation.setter
    def rotation(self, degrees: int):
        self.view.degrees = degrees % 360

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
        step the display rotation by the given signed degrees - a
        view operation only: the magnifying frame stays anchored to
        the sensor area it frames

        Args:
            delta (int): degrees to add, positive turns clockwise
        """
        self.view.turn(delta)

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
        position the magnifying frame center from a display point -
        the center is stored on the standard grid so the framed
        sensor area survives display rotation

        Args:
            fx (float): horizontal center as fraction of the display
            fy (float): vertical center as fraction of the display
        """
        cx, cy = self.view.to_sensor(fx, fy)
        self.window.move_to(cx, cy)
        if self.camera_zoom:
            self.zoom_dirty = True

    def digital_factor(self) -> float:
        """
        the enlargement factor above the camera's native zoom level -
        levels beyond it are served as digital enlargement of the
        native window as in EOS Utility

        Returns:
            float: 1.0 at or below the native level
        """
        factor = 1.0
        if self.calibration and self.zoom_level > self.calibration.native_zoom_level:
            factor = self.zoom_level / self.calibration.native_zoom_level
        return factor

    def magnify_window(self) -> Window:
        """
        the magnifying frame on the standard grid with its size
        refreshed - the measured native window fraction, shrunk by
        the digital factor; the 1/level model is the fallback for
        uncalibrated cameras

        Returns:
            Window: the magnifying frame in sensor fractions
        """
        if self.calibration:
            factor = self.digital_factor()
            width, height = self.calibration.window_fraction
            wx = width / factor
            wy = height / factor
        else:
            wx = 1.0 / self.zoom_level
            wy = 1.0 / self.zoom_level
        self.window.resize(wx, wy)
        return self.window

    def native_top_left(self) -> Tuple[float, float]:
        """
        the desired top-left of the camera's native window - at a
        digital level the small drawn window sits centered in the
        native window, so the native window is positioned to share
        its center

        Returns:
            Tuple[float, float]: (x0, y0) fractions
        """
        window = self.magnify_window()
        geometry = self.calibration.geometry
        x0 = window.cx - geometry.window_width / 2
        y0 = window.cy - geometry.window_height / 2
        return x0, y0

    def display_box(self) -> Tuple[float, float, float, float]:
        """
        the magnifying frame as a display box for drawing - for a
        calibrated camera the box shows where the window actually is
        after the camera's clamping, not where the user wished it,
        so frame and zoom content stay in sync at the borders
        see https://github.com/WolfgangFahl/scan2wiki/issues/41

        Returns:
            Tuple[float, float, float, float]: (x0, y0, width, height)
                display fractions
        """
        window = self.magnify_window()
        if self.calibration:
            geometry = self.calibration.geometry
            command = self.commanded_pixels()
            nx0, ny0 = geometry.achieved(*command)
            # drawn window shares the achieved native window center
            cx = nx0 + geometry.window_width / 2
            cy = ny0 + geometry.window_height / 2
            box = (
                cx - window.width / 2,
                cy - window.height / 2,
                window.width,
                window.height,
            )
        else:
            box = window.box()
        display = self.view.box_to_display(*box)
        return display

    def commanded_pixels(self) -> Optional[Tuple[int, int]]:
        """
        the zoom position value actually sent to the camera - for a
        calibrated model the measured per axis linear response of
        issue 41 applied to the desired native window top-left; the
        uncalibrated fallback commands the window top-left corner
        on the raw position grid

        Returns:
            Optional[Tuple[int, int]]: (x, y) position value or None
                for a backend without a zoom position entry
        """
        pixels = None
        if self.calibration:
            x0, y0 = self.native_top_left()
            pixels = self.calibration.geometry.to_command(x0, y0)
        elif self.ZOOM_POSITION_SIZE:
            window = self.magnify_window()
            grid = Grid(*self.ZOOM_POSITION_SIZE)
            pixels = grid.to_pixels(*window.top_left())
        return pixels

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
        framed area at native resolution; there is no digital zoom.
        The frame's own pixel size is the sensor window - recorded
        before the display rotation, it makes the magnifying frame
        geometry measured instead of modelled
        see https://github.com/WolfgangFahl/scan2wiki/issues/39
        """
        if not self.camera_zoom:
            raise RuntimeError(
                "camera magnification not engaged - no digital zoom is served"
            )
        if self.zoom_dirty:
            # clear before applying - the apply may leave a pending
            # position for the next frame cycle by setting the flag
            # again, see write_zoom_config
            self.zoom_dirty = False
            self.do_apply_camera_zoom()
        frame = self.do_preview_frame()
        # closed loop against silently dropped level writes: a frame
        # that does not have the calibrated zoom raster proves the
        # camera is not magnifying - re-engage with the next frame
        if self.calibration and self.calibration.zoom_raster:
            with Image.open(BytesIO(frame)) as image:
                size = list(image.size)
            self.zoom_confirmed = size == list(self.calibration.zoom_raster)
            if not self.zoom_confirmed:
                self.applied_level = 1
                self.zoom_dirty = True
        factor = self.digital_factor()
        if factor > 1.0:
            frame = self.enlarge(frame, factor)
        frame = self.apply_rotation(frame)
        return frame

    def enlarge(self, jpeg_bytes: bytes, factor: float) -> bytes:
        """
        digitally enlarge the center of the given frame by the given
        factor keeping the frame size - EOS Utility serves its 10x
        the same way from the camera's native 5x window

        Args:
            jpeg_bytes (bytes): the native zoom frame
            factor (float): the enlargement factor

        Returns:
            bytes: the enlarged JPEG
        """
        image = Image.open(BytesIO(jpeg_bytes))
        width, height = image.size
        cw, ch = width / factor, height / factor
        box = (
            (width - cw) / 2,
            (height - ch) / 2,
            (width + cw) / 2,
            (height + ch) / 2,
        )
        enlarged = image.resize((width, height), Image.LANCZOS, box=box)
        enlarged_bytes = self.to_jpeg(enlarged)
        return enlarged_bytes

    def start_camera_zoom(self) -> bool:
        """
        engage the camera's own magnification for the zoom view
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Returns:
            bool: True if the camera magnifies itself
        """
        started = self.submit(self.do_engage_zoom)
        return started

    def stop_camera_zoom(self):
        """
        release the camera's own magnification
        """
        self.submit(self.do_release_zoom)

    def refresh_full_frame(self) -> bytes:
        """
        release the camera magnification, grab one full preview and
        re-engage - a single owner thread command so that a running
        zoom stream never observes the released state

        Returns:
            bytes: the full preview JPEG with display rotation applied
        """
        return self.submit(self.do_refresh_full_frame)

    def do_refresh_full_frame(self) -> bytes:
        """
        owner thread part of refresh_full_frame
        """
        self.do_release_zoom()
        frame = self.apply_rotation(self.do_preview_frame())
        self.measure_frame(frame)
        engaged = self.do_engage_zoom()
        if not engaged:
            raise RuntimeError("camera magnification lost on full frame refresh")
        return frame

    def do_engage_zoom(self) -> bool:
        """
        backend specific engagement of the camera's own magnification
        - the base camera has none, so magnify is unavailable

        Returns:
            bool: True if the camera magnifies itself
        """
        started = False
        return started

    def do_release_zoom(self):
        """
        backend specific release of the camera's own magnification
        """
        self.camera_zoom = False

    def do_apply_camera_zoom(self):
        """
        push the current zoom level and magnifying frame position to
        the magnifying camera - no operation by default
        """
        return None

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
                f"{self.window.cx:.2f},{self.window.cy:.2f} {self.frame_no}"
            )
        else:
            text = f"mock preview {self.frame_no}"
        return self.render(text)

    def do_capture_still(self) -> bytes:
        return self.render("mock still")

    def do_engage_zoom(self) -> bool:
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

    # eoszoomposition is addressed in full-size image coordinates -
    # 3888x2592 for the Canon EOS 1000D; the former 8192x8192 guess
    # made every position overshoot and clamp to the same wrong spot
    # see https://github.com/WolfgangFahl/scan2wiki/issues/39
    ZOOM_POSITION_SIZE = (3888, 2592)

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
                self.load_calibration()
                return
            except gp.GPhoto2Error as ex:
                last_err = ex
                self.camera = None
                time.sleep(0.3)
        raise last_err

    def load_calibration(self):
        """
        resolve the measured magnify constants for the connected
        camera model from cameras.yaml - an unknown model runs
        uncalibrated with the top-left position model
        see https://github.com/WolfgangFahl/scan2wiki/issues/41
        """
        if self.calibration:
            return
        root = self.camera.get_config()
        node = self._cfg_node(root, "cameramodel")
        # gphoto2 widgets can be falsy - test against None as everywhere
        model = str(node.get_value()) if node is not None else ""
        calibrations = CameraCalibrations.get_instance()
        self.calibration = (calibrations.cameras or {}).get(model)
        if self.calibration is None:
            logger.warning(f"no magnify calibration for camera model '{model}'")

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

    def write_zoom_config(self) -> bool:
        """
        engage the camera magnification and position the magnifying
        frame - the camera honors eoszoomposition only while it
        magnifies (measured on the ruler scene 2026-08-23, issue
        41), so the level is written first and the position second,
        each on a fresh config root with the 50ms settle of the
        pyDSLR pattern. A position write while released or a level
        rewrite at the running level are skipped: the first is
        dropped by the camera, the second recenters the window

        Returns:
            bool: True if the camera supports eoszoom
        """
        # a level write on a camera without live view is dropped, so
        # the viewfinder is switched on first and given time to start
        was_on = self.viewfinder_on
        self.set_viewfinder(True)
        if not was_on:
            time.sleep(0.5)
        root = self.camera.get_config()
        node = self._cfg_node(root, "eoszoom")
        supported = node is not None
        if supported:
            # the camera magnifies only at its native level - higher
            # levels are digital enlargement as in EOS Utility
            native = self.zoom_level
            if self.calibration:
                native = min(self.zoom_level, self.calibration.native_zoom_level)
            if self.applied_level != native:
                node.set_value(str(native))
                self.settle_config(root)
                self.applied_level = native
                # the camera ignores a position sent while it is
                # still engaging - leave the position pending for
                # the next frame cycle
                self.zoom_confirmed = False
                self.zoom_dirty = True
            elif self.calibration and not self.zoom_confirmed:
                # engagement not proven by a served frame yet - keep
                # the position pending
                self.zoom_dirty = True
            else:
                position_root = self.camera.get_config()
                position = self._cfg_node(position_root, "eoszoomposition")
                if position is not None:
                    x, y = self.commanded_pixels()
                    position.set_value(f"{x},{y}")
                    # the widget always reads back 0,0 - without the
                    # forced changed flag a commanded 0,0 is
                    # silently dropped as unchanged
                    position.set_changed(True)
                    self.settle_config(position_root)
        return supported

    def settle_config(self, root):
        """
        write the given config to the camera after a short settle -
        pyDSLR sleeps before gp_camera_set_config to avoid I/O errors
        """
        time.sleep(0.05)
        self.camera.set_config(root)

    def do_engage_zoom(self) -> bool:
        """
        magnify on the camera via the eoszoom config entry with the
        magnifying frame position sent along via eoszoomposition
        see https://github.com/WolfgangFahl/scan2wiki/issues/39

        Returns:
            bool: True if the camera magnifies itself
        """

        def op() -> bool:
            self.ensure_open()
            return self.write_zoom_config()

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
            self.write_zoom_config()

        self.with_retry(op)

    def do_release_zoom(self):
        """
        release the camera's own magnification via eoszoom
        """

        def op():
            self.ensure_open()
            root = self.camera.get_config()
            node = self._cfg_node(root, "eoszoom")
            if node is not None:
                node.set_value("1")
                # settle like every other zoom write - an unsettled
                # release is dropped by the camera and the live view
                # stays magnified
                self.settle_config(root)
                self.applied_level = 1
                self.zoom_confirmed = False

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
