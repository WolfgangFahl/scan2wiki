"""
Created on 2023-11-17

@author: wf
"""

from ngwidgets.lod_grid import GridConfig, ListOfDictsGrid
from ngwidgets.widgets import Link
from nicegui import ui

from scan.dms import EntityManager


class EntityManagerView:
    """
    a view for a given entity manager
    """

    def __init__(self, em: EntityManager, key_col: str = "name", debug: bool = False):
        self.em = em
        self.key_col = key_col
        self.debug = debug
        self.title = self.em.entityPluralName
        self.setup_view()

    def setup_view(self):
        """
        set up my view elements
        """
        grid_config = GridConfig(
            key_col=self.key_col,  # Adjust this to the appropriate key column for your data
            editable=False,
            multiselect=True,
            with_buttons=False,
            debug=self.debug,
        )
        ui.label(self.title)
        self.lod_grid = ListOfDictsGrid(config=grid_config)

    def linkColumn(self, name, record, formatWith=None, formatTitleWith=None):
        """
        replace the column with the given name with a link
        """
        if name in record:
            value = record[name]
            if value is None:
                record[name] = ""
            else:
                if formatWith is None:
                    lurl = value
                else:
                    lurl = formatWith % value
                if formatTitleWith is None:
                    title = value
                else:
                    title = formatTitleWith % value
                record[name] = Link.create(lurl, title)

    def defaultRowHandler(self, row):
        self.linkColumn("url", row, formatWith="%s")

    def show(self, rowHandler=None, lodKeyHandler=None):
        """
        show my given entity manager
        """
        records = self.em.getList()
        if len(records) > 0:
            firstRecord = records[0]
            lodKeys = list(firstRecord.getJsonTypeSamples()[0].keys())
        else:
            lodKeys = ["url"]
        if lodKeyHandler is not None:
            lodKeyHandler(lodKeys)
        dictList = [vars(d).copy() for d in records]
        if rowHandler is None:
            rowHandler = self.defaultRowHandler
        for row in dictList:
            rowHandler(row)
        self.lod_grid.load_lod(dictList)
        self.lod_grid.set_checkbox_selection(self.key_col)
