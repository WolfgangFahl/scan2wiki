"""
Created on 2023-11-14

@author: wf
"""
from nicegui import ui
from scan.dms import Document
from datetime import datetime
from ngwidgets.widgets import Link
from nicegui.run import cpu_bound
from ngwidgets.background import BackgroundTaskHandler
from ngwidgets.progress import NiceguiProgressbar

class UploadForm:
    """
    upload form
    """
    def __init__(self,webserver,wiki_users:dict,path:str):
        """
        constructor
        """
        self.red_link="color: red;text-decoration: underline;"
        self.blue_link="color: blue;text-decoration: underline;"
        self.webserver=webserver
        self.scandir=self.webserver.scandir
        self.scans=self.webserver.scans
        self.wiki_users=wiki_users
        self.path=path
        self.doc=Document()
        self.doc.fromFile(folderPath=self.scandir, file=path, local=True, withOcr=False)
        self.setup_form()
        
    def setup_form(self):
        """
        setup the upload form
        """
        self.progressbar = NiceguiProgressbar(100,"work on PDF pages","steps")
        with ui.splitter() as splitter:
            with splitter.before:
                with ui.card().tight():
                    with ui.card_section():
                        self.submit = ui.button('upload', on_click=self.submit_form)
                        self.ocr=ui.button("ocr",on_click=self.run_ocr)
                    with ui.card_section():   
                        self.page_title = ui.input('pagetitle', on_change=self.update).props("size=80").bind_value_to(self.doc,"pageTitle")
                        self.page_link = ui.html('pagelink').style(self.red_link) 
                        wiki_selection=list(sorted(self.wiki_users.keys()))
                        self.wiki_user_select = self.webserver.add_select(title='Wiki',selection=wiki_selection,on_change=self.update)  
                        scanned_file_link=self.scans.get_file_link(self.path)
                        self.scanned_file_link = ui.html(scanned_file_link).style(self.blue_link)    
                        current_date = datetime.now()
                        self.categories = ui.input('categories',value=str(current_date.year)).bind_value_to(self.doc,"categories")
                        self.topic = ui.input('topic',value="OCRDocument").bind_value_to(self.doc, "topic")
            with splitter.after as self.pdf_container:
                self.pdf_view=ui.html("pdf_view").classes("w-full h-screen")
                self.ocr_text_area = ui.textarea('Text').props('clearable').props("rows=15;cols=60").bind_value_to(self.doc,"ocrText")
  
    async def run_ocr(self):
        """
        run the optical character recognition
        """
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
            self.page_link.style(self.red_link)

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
        self.page_link.style(self.blue_link)
        pass
