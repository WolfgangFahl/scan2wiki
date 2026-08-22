"""
Created on 2026-08-20

hardware-free tests for the cam2web module
see https://github.com/WolfgangFahl/scan2wiki/issues/33
and https://github.com/WolfgangFahl/scan2wiki/issues/35

@author: wf
"""

import threading

from ngwidgets.basetest import Basetest

from scan.cam2web import Cam2WebServer, GPhoto2Camera, MockCamera


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

    def test_zoom_view(self):
        """
        test the issue 39 zoom view: the digital fallback crops the
        magnifying frame out of the preview and scales it back up
        """
        import fitz

        camera = MockCamera()
        full_frame = camera.preview_frame()
        self.assertEqual((768, 512), camera.frame_size)
        camera.set_zoom(10)
        camera.set_zoom_position(0.25, 0.25)
        zoomed_frame = camera.preview_frame()
        self.assertTrue(zoomed_frame.startswith(b"\xff\xd8"))
        pix = fitz.Pixmap(zoomed_frame)
        # the crop is scaled back up to the full frame pixel size
        self.assertEqual(768, pix.width)
        self.assertEqual(512, pix.height)
        self.assertNotEqual(full_frame, zoomed_frame)
        camera.shutdown()

    def test_zoom_level_validation(self):
        """
        test that only the EOS Utility zoom levels are accepted
        """
        camera = MockCamera()
        with self.assertRaises(ValueError):
            camera.set_zoom(3)
        camera.shutdown()

    def test_zoom_position_mapping(self):
        """
        test that the magnifying frame is clamped to the frame
        borders and that a click on a running zoom view is mapped
        back into the full frame
        """
        camera = MockCamera()
        # position the magnifying frame on the full view first
        camera.set_zoom_position(0.0, 0.0)
        camera.set_zoom(10)
        # the frame is clamped to the border
        x0, y0, width, height = camera.crop_fractions()
        self.assertEqual(0.0, x0)
        self.assertEqual(0.0, y0)
        self.assertAlmostEqual(0.1, width)
        self.assertAlmostEqual(0.1, height)
        # a click on the center of the running zoom view keeps the crop
        camera.set_zoom_position(0.5, 0.5)
        self.assertAlmostEqual(0.05, camera.zoom_fx)
        self.assertAlmostEqual(0.05, camera.zoom_fy)
        self.assertEqual((0.0, 0.0), camera.crop_fractions()[:2])
        camera.shutdown()

    def test_zoom_position_units(self):
        """
        test the mapping of magnifying frame fractions to the
        eoszoomposition coordinate space
        """
        camera = CountingCamera()
        self.assertEqual((4096, 4096), camera.zoom_position(0.5, 0.5))
        self.assertEqual((0, 0), camera.zoom_position(0.0, 0.0))
        camera.shutdown()

    def test_config(self):
        """
        test the cam2web server configuration
        """
        config = Cam2WebServer.get_config()
        self.assertEqual("cam2web", config.short_name)
        self.assertEqual(8088, config.default_port)
        self.assertEqual("cam2web", config.version.name)
