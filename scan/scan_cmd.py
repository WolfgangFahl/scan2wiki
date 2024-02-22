"""
Created on 2023-11-14

@author: wf
"""
import sys
from argparse import ArgumentParser

from ngwidgets.cmd import WebserverCmd

from scan.scan_webserver import ScanWebServer, ScanSolution


class ScanCmd(WebserverCmd):
    """
    Command line for scan2wiki web server
    """

    def getArgParser(self, description: str, version_msg) -> ArgumentParser:
        """
        override the default argparser call
        """
        parser = super().getArgParser(description, version_msg)
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="show verbose output [default: %(default)s]",
        )
        parser.add_argument(
            "-rp",
            "--root_path",
            default=ScanSolution.examples_path(),
            help="path to example pdf files [default: %(default)s]",
        )
        parser.add_argument(
            "-wc", "--webcam", help="url of webcam for scans [default: %(default)s]"
        )
        return parser


def main(argv: list = None):
    """
    main call
    """
    cmd = ScanCmd(config=ScanWebServer.get_config(), webserver_cls=ScanWebServer)
    exit_code = cmd.cmd_main(argv)
    return exit_code


DEBUG = 0
if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-d")
    sys.exit(main())
