'''
Created on 2023-11-17

@author: wf
'''
from lodstorage.jsonable import JSONAble
from lodstorage.entity import EntityManager 
from ngwidgets.lod_grid import ListOfDictsGrid
from ngwidgets.widgets import Link

class EntityView():
    """
    """
    
    def __init__(self,entity:JSONAble):
        """
        
        """
        self.entity=entity
        
class EntityManagerView():
    """
    a view for a given entity manager
    """
    
    def __init__(self,em:EntityManager):
        self.em=em
        self.setup_view()
        
    def setup_view(self):
        """
        set up my view elements
        """
        self.lod_grid=ListOfDictsGrid()
        
    def linkColumn(self,name,record,formatWith=None,formatTitleWith=None):
        '''
        replace the column with the given name with a link
        '''
        if name in record:
            value=record[name]
            if value is None:
                record[name]=''
            else:
                if formatWith is None:
                    lurl=value
                else:
                    lurl=formatWith % value
                if formatTitleWith is None:
                    title=value
                else:
                    title=formatTitleWith % value
                record[name]=Link.create(lurl,title)
        
    def defaultRowHandler(self,row):
        self.linkColumn('url',row, formatWith="%s")
   
        
    def show(self,rowHandler=None,lodKeyHandler=None):
        '''
        show my given entity manager
        '''
        records=self.em.getList()
        if len(records)>0:
            firstRecord=records[0]
            lodKeys=list(firstRecord.getJsonTypeSamples()[0].keys())
        else:
            lodKeys=["url"]
        if lodKeyHandler is not None:
            lodKeyHandler(lodKeys)
        tableHeaders=lodKeys            
        dictList=[vars(d).copy() for d in records]
        if rowHandler is None:
            rowHandler=self.defaultRowHandler
        for row in dictList:
            rowHandler(row)
        title=self.em.entityPluralName
        self.lod_grid.load_lod(dictList)
        #return self.render_template(templateName=template,title=title,activeItem=title,dictList=dictList,lodKeys=lodKeys,tableHeaders=tableHeaders)
        
