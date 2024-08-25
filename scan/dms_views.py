"""
Created on 2024-08-25

@author: wf
"""
from lodstorage.jsonable import JSONAble
from nicegui import ui, run
from ngwidgets.progress import Progressbar, NiceguiProgressbar
#from ngwidgets.lod_grid import ListOfDictsGrid

class EntityView:
    """
    a generic entity view
    """

    def __init__(self, solution, entity: JSONAble):
        """
        """
        self.solution = solution
        self.entity = entity

class ArchiveView(EntityView):
    """
    show a single archive
    """

    def __init__(self, solution, archive: JSONAble):
        super().__init__(solution, archive)

    def show(self):
        self.archive=self.entity
        self.progress_bar = NiceguiProgressbar(
                total=100, desc="folders and files", unit="%"
        )
        ui.label(f"Archive: {self.archive.name}").classes('text-h4')
        self.scan_button = (
            ui.button("Collect", icon="scanner", color="primary")
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
        am = self.solution.webserver.am
        # Prepare managers
        self.solution.webserver.fm.getInstance()
        self.solution.webserver.dm.getInstance()

        # Start the scanning process
        am.addFilesAndFoldersForArchive(self.archive, progress_bar=self.progress_bar,store=True)

        ui.notify(f"Collection completed for archive: {self.archive.name}")