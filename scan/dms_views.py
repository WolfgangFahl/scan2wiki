"""
Created on 2024-08-25

@author: wf
"""

from lodstorage.jsonable import JSONAble
from ngwidgets.progress import NiceguiProgressbar
from ngwidgets.widgets import Link
from nicegui import run, ui

# from ngwidgets.lod_grid import ListOfDictsGrid


class EntityView:
    """
    a generic entity view
    """

    def __init__(self, solution, entity: JSONAble):
        """ """
        self.solution = solution
        self.entity = entity


class ArchiveView(EntityView):
    """
    show a single archive
    """

    def __init__(self, solution, archive: JSONAble):
        super().__init__(solution, archive)
        self.am = self.solution.webserver.am

    def show(self):
        """
        show the given archive
        """
        self.archive = self.entity
        with ui.row() as self.progress_row:
            self.progress_bar = NiceguiProgressbar(
                total=100, desc="folders and files", unit="%"
            )
        link = Link.create(url=self.archive.url, text=self.archive.name)
        markup = f"{link}"
        self.overview = ui.html(markup)
        # https://fonts.google.com/icons?icon.set=Material+Icons
        self.scan_button = (
            ui.button("Collect", icon="folder_special", color="primary")
            .tooltip("Start collecting folders and files for this archive")
            .on("click", handler=self.on_collect)
        )

    async def on_collect(self, _event):
        """
        Handle the collection process for the archive.
        """
        try:
            await run.io_bound(self.perform_collect)
        except Exception as ex:
            self.solution.handle_exception(ex)

    def perform_collect(self):
        """
        Perform the actual collection process.
        """
        # Prepare managers
        self.solution.webserver.fm.getInstance()
        self.solution.webserver.dm.getInstance()

        # Start the scanning process
        with self.progress_row:
            ui.notify(f"collecting files and folders for {self.archive.name}")
            self.am.addFilesAndFoldersForArchive(
                self.archive, progress_bar=self.progress_bar, store=True
            )

            ui.notify(f"Collection completed for archive: {self.archive.name}")
