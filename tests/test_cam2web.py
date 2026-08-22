"""
Created on 2026-08-20

hardware-free tests for the cam2web module
see https://github.com/WolfgangFahl/scan2wiki/issues/33
and https://github.com/WolfgangFahl/scan2wiki/issues/35

@author: wf
"""

import threading
from io import BytesIO

from ngwidgets.basetest import Basetest
from PIL import Image

from scan.cam2web import Cam2WebServer, Camera, GPhoto2Camera, MagnifyState, MockCamera


class CountingCamera(GPhoto2Camera):
    """
    gphoto2 camera with the libgphoto2 calls replaced by counters -
    proves the session handling without touching hardware
    """

    def __init__(self):
        super().__init__()
        self.counts = {"init": 0, "exit": 0, "viewfinder": 0}
        self.settings = {"iso": {"value": "Auto", "choices": ["Auto", "100"]}}

    def open(self):
        self.counts["init"] += 1
        self.camera = object()

    def close(self):
        if self.camera:
            self.counts["exit"] += 1
            self.camera = None

    def set_viewfinder(self, on: bool):
        if self.viewfinder_on == on:
            return
        self.ensure_open()
        self.check_transition_rate()
        self.counts["viewfinder"] += 1
        self.viewfinder_on = on

    def do_preview_frame(self) -> bytes:
        self.set_viewfinder(True)
        return b"\xff\xd8preview\xff\xd9"

    def do_capture_still(self) -> bytes:
        was_on = self.viewfinder_on
        self.set_viewfinder(False)
        try:
            jpeg_bytes = b"\xff\xd8still\xff\xd9"
        finally:
            if was_on:
                self.set_viewfinder(True)
        return jpeg_bytes

    def do_read_settings(self) -> dict:
        self.ensure_open()
        return self.settings

    def do_write_setting(self, key: str, value: str):
        self.ensure_open()
        self.settings[key]["value"] = value


class TestCam2Web(Basetest):
    """
    test the cam2web module without camera hardware
    """

    def test_mock_camera(self):
        """
        test that the mock camera yields valid JPEG frames and stills
        """
        camera = MockCamera()
        for jpeg_bytes in (camera.preview_frame(), camera.capture_still()):
            self.assertTrue(jpeg_bytes.startswith(b"\xff\xd8"))
            self.assertTrue(jpeg_bytes.endswith(b"\xff\xd9"))
        camera.shutdown()

    def test_commands_are_serialized(self):
        """
        test that concurrent commands run one after the other on the
        camera owner thread
        """
        camera = MockCamera()
        results = []

        def shoot():
            results.append(camera.capture_still())

        threads = [threading.Thread(target=shoot) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(5, len(results))
        camera.shutdown()

    def test_no_session_teardown(self):
        """
        test the issue 35 acceptance criterion: one init, no exit and
        no needless viewfinder churn while stills and config commands
        interleave with a running live view
        """
        camera = CountingCamera()
        camera.MIN_TRANSITION_INTERVAL = 0.0
        # live view running
        for _ in range(3):
            camera.preview_frame()
        # a still and config commands in between
        camera.capture_still()
        camera.read_settings()
        camera.write_setting("iso", "100")
        # live view continues
        for _ in range(3):
            camera.preview_frame()
        self.assertEqual(1, camera.counts["init"])
        self.assertEqual(0, camera.counts["exit"])
        # viewfinder: on for preview, off for the still, on again
        self.assertEqual(3, camera.counts["viewfinder"])
        self.assertEqual("100", camera.settings["iso"]["value"])
        camera.shutdown()

    def test_recovery(self):
        """
        test that a claim error is recovered by rebuilding the
        session once and retrying the operation
        """
        import gphoto2 as gp

        camera = CountingCamera()
        camera.MIN_TRANSITION_INTERVAL = 0.0
        camera.failures = 1

        def flaky() -> bytes:
            if camera.failures:
                camera.failures -= 1
                # could not claim the USB device - a rebuild cures this
                raise gp.GPhoto2Error(-53)
            return b"\xff\xd8ok\xff\xd9"

        camera.open()
        jpeg_bytes = camera.with_retry(flaky)
        self.assertEqual(b"\xff\xd8ok\xff\xd9", jpeg_bytes)
        # the session was rebuilt exactly once
        self.assertEqual(1, camera.counts["exit"])
        self.assertEqual(2, camera.counts["init"])
        camera.shutdown()

    def test_no_retry_for_stuck_camera(self):
        """
        test that an I/O in progress state is reported instead of
        being retried - measured on the EOS 1000D it is not cured
        by a session rebuild, only by replugging the USB cable
        """
        import gphoto2 as gp

        camera = CountingCamera()
        calls = []

        def stuck():
            calls.append(1)
            raise gp.GPhoto2Error(-110)

        camera.open()
        with self.assertRaises(gp.GPhoto2Error):
            camera.with_retry(stuck)
        # tried once, no session rebuild
        self.assertEqual(1, len(calls))
        self.assertEqual(0, camera.counts["exit"])
        self.assertIn("replug", camera.explain(gp.GPhoto2Error(-110)))
        camera.shutdown()

    def test_transition_rate_limit(self):
        """
        test that the camera is protected against viewfinder churn
        """
        camera = CountingCamera()
        camera.MIN_TRANSITION_INTERVAL = 0.0
        camera.MAX_TRANSITIONS_PER_MINUTE = 4
        with self.assertRaises(RuntimeError) as context:
            for _ in range(10):
                camera.set_viewfinder(not camera.viewfinder_on)
        self.assertIn("rate limit", str(context.exception))
        camera.shutdown()

    def jpeg_size(self, jpeg_bytes: bytes) -> tuple:
        """
        get the pixel size of the given JPEG

        Args:
            jpeg_bytes (bytes): the image data

        Returns:
            tuple: (width, height)
        """
        size = Image.open(BytesIO(jpeg_bytes)).size
        return size

    def test_zoom_view(self):
        """
        test the issue 39 acceptance criterion: the zoom view is
        served by the camera's own magnification at the selected
        level and frame position - digital zoom does not exist and
        an unengaged camera refuses to serve a zoom frame
        """
        camera = MockCamera()
        camera.preview_frame()
        self.assertEqual((768, 512), camera.frame_size)
        # without the camera magnifying there is no zoom view
        with self.assertRaises(RuntimeError):
            camera.zoom_frame()
        # engaging the camera zoom serves the framed area
        camera.set_zoom(10)
        camera.set_zoom_position(0.25, 0.25)
        self.assertTrue(camera.start_camera_zoom())
        applied = []
        camera.do_apply_camera_zoom = lambda: applied.append(
            (camera.zoom_level, camera.zoom_fx, camera.zoom_fy)
        )
        frame_10x = camera.zoom_frame()
        self.assertEqual((768, 512), self.jpeg_size(frame_10x))
        # a level change is pushed to the camera with the next frame
        camera.set_zoom(5)
        frame_5x = camera.zoom_frame()
        self.assertNotEqual(frame_10x, frame_5x)
        # a position drag is pushed to the camera with the next frame
        camera.set_zoom_position(0.75, 0.5)
        camera.zoom_frame()
        self.assertEqual([(5, 0.25, 0.25), (5, 0.75, 0.5)], applied)
        # releasing the camera zoom ends the zoom view
        camera.stop_camera_zoom()
        with self.assertRaises(RuntimeError):
            camera.zoom_frame()
        camera.shutdown()

    def test_zoom_level_validation(self):
        """
        test that only the EOS Utility zoom levels are accepted
        """
        camera = MockCamera()
        with self.assertRaises(ValueError):
            camera.set_zoom(3)
        camera.shutdown()

    def test_zoom_position_clamping(self):
        """
        test that the magnifying frame is clamped to the frame borders
        """
        camera = MockCamera()
        camera.set_zoom(10)
        camera.set_zoom_position(0.0, 0.0)
        x0, y0, width, height = camera.crop_fractions()
        self.assertEqual(0.0, x0)
        self.assertEqual(0.0, y0)
        self.assertAlmostEqual(0.1, width)
        self.assertAlmostEqual(0.1, height)
        camera.set_zoom_position(1.5, -0.5)
        self.assertEqual(1.0, camera.zoom_fx)
        self.assertEqual(0.0, camera.zoom_fy)
        camera.shutdown()

    def test_unrotate_fraction(self):
        """
        test the mapping of rotated display fractions back to sensor
        fractions for the eoszoomposition entry
        """
        camera = CountingCamera()
        point = (0.25, 0.5)
        expected = {
            0: (0.25, 0.5),
            90: (0.5, 0.75),
            180: (0.75, 0.5),
            270: (0.5, 0.25),
        }
        for rotation, sensor in expected.items():
            camera.rotation = rotation
            fx, fy = camera.unrotate_fraction(*point)
            self.assertAlmostEqual(sensor[0], fx, msg=f"rotation {rotation}")
            self.assertAlmostEqual(sensor[1], fy, msg=f"rotation {rotation}")
        camera.shutdown()

    def test_rotation(self):
        """
        test the issue 38 rotate feature: the display rotation is
        applied to preview frames and stills and the two rotate
        buttons step it in 90 degree increments
        """
        camera = MockCamera()
        camera.rotate_by(90)
        self.assertEqual(90, camera.rotation)
        self.assertEqual((512, 768), self.jpeg_size(camera.preview_frame()))
        self.assertEqual((512, 768), self.jpeg_size(camera.capture_still()))
        camera.rotate_by(-90)
        self.assertEqual(0, camera.rotation)
        camera.rotate_by(-90)
        self.assertEqual(270, camera.rotation)
        camera.shutdown()

    def test_autorotate(self):
        """
        test the issue 38 autorotate feature: a still carrying an EXIF
        orientation tag is transposed accordingly
        """

        class ExifCamera(MockCamera):
            def do_capture_still(self) -> bytes:
                image = Image.new("RGB", (768, 512))
                exif = image.getexif()
                # orientation 6: rotate 90 degrees clockwise to view
                exif[274] = 6
                buffer = BytesIO()
                image.save(buffer, "JPEG", exif=exif)
                return buffer.getvalue()

        camera = ExifCamera()
        camera.autorotate = True
        self.assertEqual((512, 768), self.jpeg_size(camera.capture_still()))
        camera.autorotate = False
        self.assertEqual((768, 512), self.jpeg_size(camera.capture_still()))
        camera.shutdown()

    def test_magnify_state(self):
        """
        test the issue 39 magnify mode transitions
        """
        state = MagnifyState()
        self.assertEqual(MagnifyState.NORMAL, state.mode)
        state.set_magnify(True)
        self.assertEqual(MagnifyState.SELECT, state.mode)
        state.click_zoom()
        self.assertEqual(MagnifyState.MAGNIFIED, state.mode)
        state.click_main()
        self.assertEqual(MagnifyState.SELECT, state.mode)
        state.set_magnify(False)
        self.assertEqual(MagnifyState.NORMAL, state.mode)

    def test_camera_zoom_required(self):
        """
        test that a camera without its own magnification refuses to
        magnify - no zoom view is ever served digitally
        """
        camera = Camera()
        camera.set_zoom(5)
        started = camera.start_camera_zoom()
        self.assertFalse(started)
        self.assertFalse(camera.camera_zoom)
        with self.assertRaises(RuntimeError):
            camera.zoom_frame()
        camera.shutdown()

    def test_config(self):
        """
        test the cam2web server configuration
        """
        config = Cam2WebServer.get_config()
        self.assertEqual("cam2web", config.short_name)
        self.assertEqual(8088, config.default_port)
        self.assertEqual("cam2web", config.version.name)
