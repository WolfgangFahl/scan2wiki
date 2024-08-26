"""
Created on 2023-11-14

@author: wf
"""
import logging
import os
import sys

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from ngwidgets.input_webserver import InputWebserver, InputWebSolution
from ngwidgets.lod_grid import ListOfDictsGrid, GridConfig
from ngwidgets.webserver import WebserverConfig
from nicegui import Client, app, ui
from wikibot3rd.wikiuser import WikiUser

from scan.dms import (
    ArchiveManager,
    DMSStorage,
    Document,
    DocumentManager,
    FolderManager,
)
from scan.entity_view import EntityManagerView
from scan.dms_views import ArchiveView
from scan.scans import Scans
from scan.upload import UploadForm
from scan.version import Version
from scan.webcam import WebcamForm

class ScanWebServer(InputWebserver):
    """
    server for Document Management system with option to scan to Semantic Mediawikis
    """

    @classmethod
    def get_config(cls) -> WebserverConfig:
        """
        get the configuration for this Webserver
        """
        copy_right = "(c)2020-2024 Wolfgang Fahl"
        config = WebserverConfig(
            copy_right=copy_right,
            version=Version(),
            default_port=8334,
            short_name="scan2wiki",
            timeout=10.0
        )
        server_config = WebserverConfig.get(config)
        server_config.solution_class = ScanSolution
        return server_config

    def __init__(self):
        """Constructs all the necessary attributes for the WebServer object."""
        InputWebserver.__init__(self, config=ScanWebServer.get_config())
        self.scandir = DMSStorage.getScanDir()
        self.scans = Scans(self.scandir)
        self.wiki_users = WikiUser.getWikiUsers()
        self.sql_db = DMSStorage.getSqlDB()
        self.am = ArchiveManager.getInstance()
        self.fm = FolderManager.getInstance()
        self.dm = DocumentManager.getInstance()

        @ui.page("/upload/{path:path}")
        async def upload(client: Client, path: str = None):
            return await self.page(
                client, ScanSolution.upload,path
            )

        @ui.page("/webcam")
        async def webcam(client: Client):
            return await self.page(
                client, ScanSolution.webcam
            )

        @ui.page("/archives")
        async def show_archives(client: Client):
            return await self.page(
                client, ScanSolution.show_archives
            )

        @ui.page("/archive/{archive_id:str}")
        async def show_archive(client: Client, archive_id: str):
            return await self.page(
                client, ScanSolution.show_archive, archive_id
            )

        @app.get("/delete/{path:path}")
        def delete(path: str = None):
            self.scans.delete(path)
            return RedirectResponse("/")

        @app.route("/files")
        @app.get("/files/{path:path}")
        def files(path: str = "."):
            return self.files(path)

    def files(self, path: str = "."):
        """
        show the files in the given path

        Args:
            path (str): the path to render
        """
        fullpath = f"{self.scandir}/{path}"
        if os.path.isdir(fullpath):
            self.scans = Scans(fullpath)
            return RedirectResponse("/")
        elif os.path.isfile(fullpath):
            file_response = FileResponse(fullpath)
            return file_response
        else:
            msg = f"invalid path: {path}"
            return HTMLResponse(content=msg, status_code=404)

class ScanSolution(InputWebSolution):
    """
    the Scan solution
    """

    def __init__(self, webserver: ScanWebServer, client: Client):
        """
        Initialize the solution

        Calls the constructor of the base solution
        Args:
            webserver (ScanWebServer): The webserver instance associated with this context.
            client (Client): The client instance this context is associated with.
        """
        super().__init__(webserver, client)  # Call to the superclass constructor
        self.stdout_handler = logging.StreamHandler(stream=sys.stdout)
        self.stderr_handler = logging.StreamHandler(stream=sys.stderr)

    async def setup_footer(self):
        """
        add handlers for stdout and stderr
        """
        await super().setup_footer(
            with_log=True,
            handle_logging=False,
            max_lines=100,
            log_classes="w-full h-20",
        )

    async def webcam(self):
        def setup_webcam():
            self.webcam_form = WebcamForm(self, self.args.webcam)

        await self.setup_content_div(setup_webcam)

    async def upload(self, path: str = None):
        """
        handle upload requests
        """

        def setup_upload_form():
            if path:
                ui.notify(f"upload of {path} requested")
            self.upload_form = UploadForm(self, self.webserver.wiki_users, path)

        await self.setup_content_div(setup_upload_form)

    @classmethod
    def examples_path(cls) -> str:
        # the root directory (default: examples)
        path = os.path.join(os.path.dirname(__file__), "../scan2wiki_examples")
        path = os.path.abspath(path)
        return path

    def update_scans(self):
        """
        update the scans grid
        """
        try:
            lod = self.webserver.scans.get_scan_files()
            self.lod_grid.load_lod(lod)
            self.lod_grid.sizeColumnsToFit()
            self.lod_grid.set_checkbox_selection(self.key_col)
        except Exception as ex:
            self.handle_exception(ex)

    async def show_archive(self, archive_id: str):
        """
        show the archive with the given id
        """
        def setup_show_archive():
            archive = self.webserver.am.archives_by_name.get(archive_id)
            if archive:
                archive_view = ArchiveView(self,archive)
                archive_view.show()
            else:
                ui.label(f"Archive with id {archive_id} not found")

        await self.setup_content_div(setup_show_archive)

    async def show_archives(self):
        """
        show archives
        """

        def setup_show_archives():
            """
            show the archives
            """
            def row_handler(row):
                # First, call the default row handler
                am_view.defaultRowHandler(row)
                # Then, add our custom link for the 'name' column
                am_view.linkColumn("name", row, formatWith="/archive/%s", formatTitleWith="%s")
            am_view = EntityManagerView(self.webserver.am,key_col="name")
            am_view.show(rowHandler=row_handler)

        await self.setup_content_div(setup_show_archives)

    def configure_menu(self):
        """
        configure additional non-standard menu entries
        """
        self.link_button(name="Webcam", icon_name="photo_camera", target="/webcam")
        self.link_button(name="Archives", icon_name="database", target="/archives")
        pass

    async def on_work_click(self):
        ui.notify("work requested")

    async def home(self):
        """
        provide the main content page
        """

        def setup_home():
            self.key_col="#"
            grid_config = GridConfig(
                key_col=self.key_col,
                editable=True,
                multiselect=True,
                with_buttons=False,
                debug=self.args.debug
            )
            self.lod_grid = ListOfDictsGrid(config=grid_config)
            self.lod_grid.setup_button_row(["all","fit"])
            with self.lod_grid.button_row:
                self.work_button = ui.button("work", on_click=self.on_work_click)

            self.update_scans()

        await (self.setup_content_div(setup_home))
