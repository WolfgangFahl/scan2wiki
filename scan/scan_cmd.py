"""
Created on 2023-11-14

@author: wf
"""

import sys
from argparse import ArgumentParser

from basemkit.argparse_action import StoreDictKeyPair
from ngwidgets.cmd import WebserverCmd

from scan.scan_webserver import ScanSolution, ScanWebServer


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
            "-rp",
            "--root_path",
            default=ScanSolution.examples_path(),
            help="path to example pdf files [default: %(default)s]",
        )
        parser.add_argument(
            "-wc",
            "--webcams",
            action=StoreDictKeyPair,
            help="webcams as name-url pairs in the format name1=url1,name2=url2",
        )
        parser.add_argument(
            "--web-host", default="z", help="Web server hostname or IP."
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
