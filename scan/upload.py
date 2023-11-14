"""
Created on 2023-11-14

@author: wf
"""
from nicegui import ui
from scan.dms import Document
from datetime import datetime

class UploadForm:
    """
    upload form
    """
    def __init__(self,webserver,wiki_users:dict,path:str):
        """
        constructor
        """
        self.webserver=webserver
        self.scandir=self.webserver.scandir
        self.doc=Document()
        self.doc.fromFile(folderPath=self.scandir, file=path, local=True, withOcr=False)
        self.submit = ui.button('upload', on_click=self.submit_form)
        self.ocr=ui.button("ocr",on_click=self.run_ocr)
        self.page_title = ui.input('pagetitle', on_change=self.update).props("size=80").bind_value_to(self.doc,"pageTitle")
        self.page_link = ui.label('pagelink').props("size=80")
        wiki_selection=list(sorted(wiki_users.keys()))
        self.wiki_user = webserver.add_select('Wiki', wiki_selection)  
        self.scanned_file = ui.input('scannedFile',value=path).props("size=80")    
        current_date = datetime.now()
        self.categories = ui.input('categories',value=str(current_date.year))
        self.topic = ui.input('topic',value="OCRDocument").bind_value_to(self.doc, "topic")
        self.ocr_text = ui.textarea('Text').props('clearable').props("rows=15;cols=60")
  
    async def run_ocr(self):
        ui.notify("Optical Character Recognition requested ...")
        
    def update(self):
        """
        update the page_link dependend on the page text
        """
        page_title = self.page_title.value
        wiki_link = f"http://{self.wiki_user.value}.bitplan.com/index.php/{page_title}"
        self.page_link.set_text(wiki_link)

    def to_document(self, scandir,withOcr:bool=False):
        """
        convert my content to a document
        """
        doc = Document()  
        doc.fromFile(scandir, self.scanned_file.value, local=True,withOcr=withOcr)
        doc.wikiUser = self.wiki_user.value
        doc.categories = self.categories.value
        if not withOcr:
            doc.ocrText=self.ocr_text.value
        return doc

    def submit_form(self):
        """
        actually do the upload
        """
        uploadDoc=self.to_document(self.scandir,withOcr=False)
        uploadDoc.uploadFile(self.wiki_user.value)
        pass
