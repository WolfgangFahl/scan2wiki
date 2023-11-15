"""
Created on 2023-11-14

@author: wf
"""
from nicegui import ui
from scan.dms import Document
from datetime import datetime
from ngwidgets.widgets import Link
from ngwidgets.background import BackgroundTaskHandler
from ngwidgets.progress import NiceguiProgressbar
import logging
import time
from collections import Counter

class TimeMessage():
    
    def __init__(self,start_msg:str,finish_msg:str=None):
        self.start_msg=start_msg
        if finish_msg is None:
            finish_msg="finished after"
        self.finish_msg=finish_msg
        self.start_time=time.time()
        
    def __str__(self):
        return self.start_msg
    
    def done(self)->str:
        end_time=time.time()
        duration=end_time-self.start_time
        done_msg=f"{self.start_msg} {self.finish_msg} {duration:.1f} secs"
        return done_msg

class UploadLogFilter(logging.Filter):
    """
    logging filter for the Uploadform
    """
    def __init__(self, progressbar):
        super(UploadLogFilter, self).__init__()
        self.progressbar = progressbar
        self.reset()
        
    def reset(self,progress_step:int=1,per_log:int=250):
        self.progressbar.reset()
        self.progress_step=progress_step
        self.per_log=per_log
        self.module_counter=Counter()
        
    def show_stats(self,log_view):
        """
        """
        stats = self.module_counter.most_common()  # Get the most common modules
        stats_str = "\n".join([f"{module}: {count} logs" for module, count in stats])
        if log_view:
            log_view.push(stats_str)
        pass
        
    def filter(self, record):
        self.module_counter[record.module]+=1
        if sum(self.module_counter.values()) % self.per_log == 0:
            self.progressbar.update(self.progress_step)  # Increment progress bar by stepsize
        msg=str(record.msg).lower()    
        # make sure errors are still shown
        if "error" in msg:
            return False
        return True # Prevent standard logging

class UploadForm:
    """
    upload form
    """
    def __init__(self,webserver,wiki_users:dict,path:str):
        """
        constructor
        """
        self.rem_value = 48  # Default rem value           
        self.task_handler = BackgroundTaskHandler()
        self.red_link="color: red;text-decoration: underline;"
        self.blue_link="color: blue;text-decoration: underline;"
        self.webserver=webserver
        self.debug=self.webserver.debug
        self.scandir=self.webserver.scandir
        self.scans=self.webserver.scans
        self.wiki_users=wiki_users
        self.path=path
        self.doc=Document()
        self.doc.fromFile(folderPath=self.scandir, file=path, local=True, withOcr=False)
        self.setup_form()
        self.upload_log_filter = UploadLogFilter(self.progressbar)
        self.webserver.logger.addHandler(self.webserver.stdout_handler)
        self.webserver.logger.addHandler(self.webserver.stderr_handler)
        for logger_name in logging.Logger.manager.loggerDict:
            #print(logger_name)
            logger=logging.getLogger(logger_name)
            logger.propagate=True
            logger.addFilter(self.upload_log_filter)
        
        self.uploaded=False
        #self.pdfminer_logger = logging.getLogger('pdfminer')
        #self.webserver.logger.addHandler(self.pdfminer_logger)
        
    def setup_form(self):
        """
        setup the upload form
        """
        with ui.splitter(value=30).classes("h-fit").style("flex:1") as self.splitter:
            with self.splitter.before:
                with ui.card().tight():
                    with ui.card_section():
                        self.progressbar = NiceguiProgressbar(100,"processing page","steps")
                        self.submit = ui.button('upload', on_click=self.run_upload)
                        self.ocr=ui.button("ocr",on_click=self.run_ocr)
                    with ui.card_section():   
                        self.page_title = ui.input('pagetitle', on_change=self.update).props("size=80").bind_value_to(self.doc,"pageTitle")
                        self.page_link = ui.html('pagelink').style(self.red_link) 
                        wiki_selection=list(sorted(self.wiki_users.keys()))
                        self.wiki_user_select = self.webserver.add_select(title='Wiki',selection=wiki_selection,on_change=self.update)  
                        self.scanned_file_url,self.scanned_file_link=self.scans.get_file_link(self.path)
                        self.scanned_file_link_view = ui.html(self.scanned_file_link).style(self.blue_link)    
                        current_date = datetime.now()
                        self.categories = ui.input('categories',value=str(current_date.year)).bind_value_to(self.doc,"categories")
                        self.topic = ui.input('topic',value="OCRDocument").bind_value_to(self.doc, "topic")
            with self.splitter.after as self.pdf_container:
                with ui.element("div").classes("w-full h-full"):
                    self.ocr_text_area = ui.textarea('Text').props('clearable').props("rows=25;cols=80").bind_value_to(self.doc,"ocrText")
                    ui.separator() 
                    self.rem_slider = ui.slider(min=10, max=100, step=1, value=self.rem_value, on_change=self.update_pdf_viewer_height)
                    # Embedding the PDF within a div that takes the full width and height
                    pdf_html = f"""<embed src="{self.scanned_file_url}" type="application/pdf" style="width:100%; height:100%;">"""
                    self.pdf_viewer = ui.html(pdf_html).classes('w-full h-[48rem]')
                        
    async def run_ocr(self):
        """
        run the optical character recognition
        """
        try:
            self.upload_log_filter.reset(1,150)
            time_msg=TimeMessage(f"OCR for {self.doc.name} ({self.doc.size})")
            ui.notify(time_msg)
            _, get_ocr_text_coro = self.task_handler.execute_in_background(self.doc.getOcrText)
            ocr_text = await get_ocr_text_coro()      
            self.ocr_text_area.value = ocr_text
            self.upload_log_filter.show_stats(self.webserver.log_view)
            ui.notify(time_msg.done())
            self.update_progress(100)
        except Exception as ex:
            self.webserver.handle_exception(ex)
        
    async def update_pdf_viewer_height(self, e):
        """
        Update the height of the PDF viewer based on the slider value.
        """
        self.rem_value = e.value
        new_height = f"h-[{self.rem_value}rem]"  # Calculate the new height in rem
        self.pdf_viewer.classes = f'w-full {new_height}'  # Update the PDF viewer height
        self.splitter.update()

    def update_progress(self, progress):
        self.progressbar.value = progress
        
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
            link_style=self.blue_link if self.uploaded else self.red_link
            self.page_link.style(link_style)

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

    async def run_upload(self):
        """
        actually do the upload
        """
        try:
            uploadDoc=self.doc
            self.upload_log_filter.reset(8,1)
            time_msg=TimeMessage(f"uploading {uploadDoc.name} ({uploadDoc.size})")
            ui.notify(time_msg)
            wiki_id=self.wiki_user_select.value
            _, upload_coro = self.task_handler.execute_in_background(uploadDoc.uploadFile, wiki_id)
            await upload_coro()
            self.upload_log_filter.show_stats(self.webserver.log_view)
            ui.notify(time_msg.done())
            #self.update_progress(100)
            self.uploaded=True
            self.update()
        except Exception as ex:
            self.webserver.handle_exception(ex)