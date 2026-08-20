"""
Created on 2026-08-20

cam2web_cmd - CLI starter for the cam2web module
see https://github.com/WolfgangFahl/scan2wiki/issues/33

@author: wf
"""

import sys
from argparse import ArgumentParser

from ngwidgets.cmd import WebserverCmd

from scan.cam2web import Cam2WebServer, Cam2WebSolution


class Cam2WebCmd(WebserverCmd):
    """
    Command line for the cam2web webcam emulator server
    """

    def getArgParser(self, description: str, version_msg) -> ArgumentParser:
        """
        override the default argparser call
        """
        parser = super().getArgParser(description, version_msg)
        parser.add_argument(
            "--camera",
            default="gphoto2",
            choices=sorted(Cam2WebServer.cameras.keys()),
            help="camera backend to use [default: %(default)s]",
        )
        parser.add_argument(
            "--fps",
            type=float,
            default=10.0,
            help="maximum frames per second for the MJPEG stream [default: %(default)s]",
        )
        return parser


def main(argv: list = None):
    """
    main call
    """
    cmd = Cam2WebCmd(
        config=Cam2WebServer.get_config(), webserver_cls=Cam2WebServer
    )
    exit_code = cmd.cmd_main(argv)
    return exit_code


DEBUG = 0
if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-d")
    sys.exit(main())
