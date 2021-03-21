'''
Created on 2021-03-21

@author: wf
'''
from datetime import datetime
import tkinter as tk
import PyPDF2
from pathlib import Path

class UploadEntry(object):
    
    def __init__(self,index,file):
        self.index=index
        self.timestamp=datetime.now()
        self.fields=[
            { "name": "pageTitle","label":"page title" },
            { "name": "scannedFile","label":"scanned file" },
            { "name": "categories","label":"categories" },
            { "name": "topic","label":"topic" },
            { "name": "ocrText","label":"ocr text","height":20}
        ]
        self.timestampStr=self.timestamp.strftime('%Y-%m-%d%H%M%S')
        self.pageTitle="scan%s-%02d" % (self.timestampStr,index+1)
        self.scannedFile=file
        self.fileName=Path(self.scannedFile).name
        
        self.categories="2021"
        self.topic="OCRDocument"
        self.ocrText=self.getPDFText()
        self.fieldTexts={}
        pass        
    
    def __str__(self):
        text="Upload:"
        delim=""
        for field in self.fields:
            fieldname=field['name']
            text+="%s%s=%s" % (delim,fieldname,self.__dict__[fieldname])   
            delim=","
        return text  
    
    def fromTk(self):
        for field in self.fields:
            fieldname=field['name']
            self.__dict__[fieldname]=self.fieldTexts[fieldname].get("1.0","end-1c")
    
    def add2Tk(self,top,row):
        for col,field in enumerate(self.fields):
            fieldname=field['name']
            if self.index==0:
                headerLabel=tk.Label(text=fieldname)
                headerLabel.grid(column=0,row=row+col)
            height=field['height'] if 'height' in field else 1
            text=tk.Text(top,height=height)
            text.insert(tk.INSERT,self.__dict__[fieldname])
            text.grid(column=1,row=row+col)
            self.fieldTexts[fieldname]=text
            
    def getPDFText(self):
        pdfText=None
        if self.scannedFile.lower().endswith("pdf"):
            pdfText=""
            pdf_file = open(self.scannedFile, 'rb')
            read_pdf = PyPDF2.PdfFileReader(pdf_file)
            number_of_pages = read_pdf.getNumPages()
            pdfText=""
            delim=""
            for pageNo in range(number_of_pages):
                page = read_pdf.getPage(pageNo)
                page_content = page.extractText()
                pdfText+=delim+page_content
                delim="\n"
        return pdfText
            
            
    def getContent(self):
        wikicats=""
        delim=""
        for category in self.categories.split(','):
            wikicats+="%s[[Category:%s]]" % (delim,category)
            delim="\n"
        if self.fileName.endswith(".pdf"):
            template="""= pdf pages =
<pdf>%s</pdf>
= text =
<pre>%s</pre>
= pdf =
[[File:%s]]
%s
<headertabs/>
""" 
            pageContent=template % (self.fileName,self.ocrText,self.fileName,wikicats)
        else:
            template="""[[File:%s]]
%s
<headertabs/>"""
            pageContent=template % (self.fileName,wikicats)
    
        return pageContent
        
        