"""
Created on 2026-08-22

measure and prove that the cam2web home page stays reachable while
the camera routes are being served
see https://github.com/WolfgangFahl/scan2wiki/issues/37

@author: wf
"""

import threading
import time
import urllib.request

from ngwidgets.basetest import Basetest
from ngwidgets.webserver_test import ThreadedServerRunner

from scan.cam2web import Cam2WebServer
from scan.cam2web_cmd import Cam2WebCmd


class TestCam2WebRoutes(Basetest):
    """
    issue 37 acceptance: with a live view stream running the home
    page loads instead of running into the connection timeout
    """

    def setUp(self, debug=False, profile=True):
        Basetest.setUp(self, debug=debug, profile=profile)
        self.config = Cam2WebServer.get_config()
        self.config.default_port += 10000
        self.cmd = Cam2WebCmd(self.config, Cam2WebServer)
        args = self.cmd.parse_args(["--camera", "mock", "--fps", "20"])
        self.ws = Cam2WebServer()
        self.server_runner = ThreadedServerRunner(self.ws, args=args, debug=self.debug)
        self.server_runner.start()
        self.base_url = f"http://localhost:{self.config.default_port}"
        self.wait_for_server()

    def tearDown(self):
        super().tearDown()
        self.server_runner.stop()

    def wait_for_server(self, timeout: float = 15.0):
        """
        wait until the threaded server answers on its port
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"{self.base_url}/", timeout=1.0)
                return
            except Exception:
                time.sleep(0.2)
        self.fail(f"server not reachable at {self.base_url}")

    def fetch_latency(self, path: str, timeout: float = 8.0) -> float:
        """
        measure how long a GET of the given path takes

        Args:
            path (str): the path to fetch
            timeout (float): socket timeout in seconds

        Returns:
            float: elapsed seconds
        """
        start = time.monotonic()
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=timeout) as r:
            r.read()
        elapsed = time.monotonic() - start
        return elapsed

    def consume_stream(self, stop: threading.Event, min_bytes: int = 20000):
        """
        consume the MJPEG stream until told to stop

        Args:
            stop (threading.Event): set to end the consumption
            min_bytes (int): bytes to read per chunk
        """
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/stream.mjpg", timeout=8.0
            ) as r:
                while not stop.is_set():
                    if not r.read(min_bytes):
                        break
        except Exception:
            pass

    def test_home_page_responsive_while_streaming(self):
        """
        issue 37 acceptance criterion: with a live view stream running
        and stills interleaving, the home page answers well below the
        10 second connection timeout
        """
        baseline = self.fetch_latency("/")
        stop = threading.Event()
        streamer = threading.Thread(target=self.consume_stream, args=(stop,))
        streamer.start()
        try:
            # let the stream run
            time.sleep(1.0)
            # a still in flight while the stream runs
            still = threading.Thread(target=self.fetch_latency, args=("/still.jpg",))
            still.start()
            latencies = []
            for _ in range(3):
                latencies.append(self.fetch_latency("/"))
            still.join(timeout=10.0)
        finally:
            stop.set()
            streamer.join(timeout=10.0)
        worst = max(latencies)
        if self.debug:
            print(f"home page latency: baseline {baseline:.3f}s worst {worst:.3f}s")
        self.assertLess(
            worst,
            2.0,
            f"home page took {worst:.1f}s while streaming - event loop is held",
        )
