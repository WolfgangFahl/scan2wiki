"""
Created on 2026-08-20

hardware-free tests for the cam2web module
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

from ngwidgets.basetest import Basetest

from scan.cam2web import Cam2WebServer, MockCamera


class TestCam2Web(Basetest):
    """
    test the cam2web module with the mock camera backend
    """

    def test_mock_camera(self):
        """
        test that the mock camera yields valid JPEG frames and stills
        """
        camera = MockCamera()
        for jpeg_bytes in (camera.preview_frame(), camera.capture_still()):
            self.assertTrue(jpeg_bytes.startswith(b"\xff\xd8"))
            self.assertTrue(jpeg_bytes.endswith(b"\xff\xd9"))

    def test_single_client(self):
        """
        test that the camera is claimed per client
        """
        camera = MockCamera()
        self.assertTrue(camera.claim())
        self.assertFalse(camera.claim())
        camera.release()
        self.assertTrue(camera.claim())
        camera.release()

    def test_config(self):
        """
        test the cam2web server configuration
        """
        config = Cam2WebServer.get_config()
        self.assertEqual("cam2web", config.short_name)
        self.assertEqual(8088, config.default_port)
        self.assertEqual("cam2web", config.version.name)
