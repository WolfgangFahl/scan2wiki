"""
Created on 2023-11-14

@author: wf
"""
from nicegui import ui
from scan.dms import Document
from datetime import datetime
from ngwidgets.widgets import Link

class UploadForm:
    """
    upload form
    """
    def __init__(self,webserver,wiki_users:dict,path:str):
        """
        constructor
        """
        self.webserver=webserver
        self.wiki_users=wiki_users
        self.scandir=self.webserver.scandir
        self.doc=Document()
        self.doc.fromFile(folderPath=self.scandir, file=path, local=True, withOcr=False)
        self.submit = ui.button('upload', on_click=self.submit_form)
        self.ocr=ui.button("ocr",on_click=self.run_ocr)
        self.page_title = ui.input('pagetitle', on_change=self.update).props("size=80").bind_value_to(self.doc,"pageTitle")
        self.page_link = ui.html('pagelink')
        wiki_selection=list(sorted(wiki_users.keys()))
        self.wiki_user_select = webserver.add_select('Wiki', wiki_selection)  
        self.scanned_file = ui.input('scannedFile',value=path).props("size=80")    
        current_date = datetime.now()
        self.categories = ui.input('categories',value=str(current_date.year)).bind_value_to(self.doc,"categories")
        self.topic = ui.input('topic',value="OCRDocument").bind_value_to(self.doc, "topic")
        self.ocr_text_area = ui.textarea('Text').props('clearable').props("rows=15;cols=60").bind_value_to(self.doc,"ocrText")
  
    async def run_ocr(self):
        ui.notify("Optical Character Recognition requested ...")
        ocr_text=self.doc.getOcrText()
        self.ocr_text_area.value=ocr_text
        
    def update(self):
        """
        update the page_link dependend on the page text or selected wiki
        """
        page_title = self.page_title.value
        wiki_id=self.wiki_user_select.value
        if wiki_id in self.wiki_users:
            wiki_user=self.wiki_users[wiki_id]
            wiki_url=f"{wiki_user.url}{wiki_user.scriptPath}"
            wiki_link = Link.create(f"{wiki_url}/index.php/{page_title}",page_title)
            self.page_link.content=wiki_link

    def to_document(self, scandir,withOcr:bool=False):
        """
        convert my content to a document
        """
        doc = Document()  
        doc.fromFile(scandir, self.scanned_file.value, local=True,withOcr=withOcr)
        doc.wikiUser = self.wiki_user_select.value
        doc.categories = self.categories.value
        if not withOcr:
            doc.ocrText=self.ocr_text_area.value
        return doc

    def submit_form(self):
        """
        actually do the upload
        """
        uploadDoc=self.doc
        wiki_id=self.wiki_user_select.value
        uploadDoc.uploadFile(wiki_id)
        pass
