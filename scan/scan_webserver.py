"""
Created on 2023-11-14

@author: wf
"""
import os
from nicegui import ui,app,Client
from ngwidgets.lod_grid import ListOfDictsGrid
from ngwidgets.input_webserver import InputWebserver
from ngwidgets.webserver import WebserverConfig
from scan.version import Version
from scan.dms import DMSStorage
from scan.scans import Scans


class ScanWebServer(InputWebserver):
    """
    server for Document Management system with option to scan to Semantic Mediawikis
    """

    @classmethod
    def get_config(cls) -> WebserverConfig:
        """
        get the configuration for this Webserver
        """
        copy_right = "(c)2020-2023 Wolfgang Fahl"
        config = WebserverConfig(
            copy_right=copy_right, version=Version(), default_port=8334
        )
        return config

    def __init__(self):
        """Constructs all the necessary attributes for the WebServer object."""
        InputWebserver.__init__(self, config=ScanWebServer.get_config())
        scandir = DMSStorage.getScanDir()
        self.scans = Scans(scandir)
        
        @app.get('/delete/{path:path}')
        def delete(path:str=None):
            return self.scans.delete(path)

    @classmethod
    def examples_path(cls) -> str:
        # the root directory (default: examples)
        path = os.path.join(os.path.dirname(__file__), "../scan2wiki_examples")
        path = os.path.abspath(path)
        return path
    
    async def update_scans(self):
        """
        update the scans grid
        """
        try:
            lod=self.scans.get_scan_files()
            self.lod_grid.load_lod(lod)
        except Exception as ex:
            self.handle_exception(ex,self.do_trace)
    
    async def home(self, _client: Client):
        """
        provide the main content page

        """
        self.setup_menu()
        self.lod_grid = ListOfDictsGrid(auto_size_columns=True)
        await self.update_scans()
        await self.setup_footer()
