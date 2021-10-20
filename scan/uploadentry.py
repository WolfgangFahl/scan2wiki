'''
Created on 2021-03-21

@author: wf
'''
from datetime import datetime
from scan.pdf import PDFMiner
import os
from pathlib import Path
from wikibot.wikipush import WikiPush

class UploadEntry(object):
    '''
    a single upload entry
    '''     
    def __init__(self,directory,path):
        '''
        construct me
        
        Args:
            
        '''
        fullpath=f"{directory}/{path}"
        ftime=datetime.fromtimestamp(os.path.getmtime(fullpath))
        self.timestampStr=ftime.strftime("%Y-%m-%d %H:%M:%S")
        self.scannedFile=fullpath
        self.fileName=Path(self.scannedFile).name
        self.baseName=Path(self.scannedFile).stem
        self.pageTitle=f"{self.baseName}"
        
        self.categories="2021"
        self.topic="OCRDocument"
        self.wikiUser="test"
        self.ocrText=self.getPDFText()
        pass        
    
    def __str__(self):
        text="Upload:"
        self.fields=['fileName','ocrText']
        delim=""
        for fieldname in self.fields:
            text+="%s%s=%s" % (delim,fieldname,self.__dict__[fieldname])   
            delim=","
        return text  
    
    def getPDFText(self):
        '''
        get my PDF Text
        '''
        pdfText=None
        if self.scannedFile.lower().endswith("pdf"):
            pdfText=PDFMiner.getPDFText(self.scannedFile)
        return pdfText
            
    def uploadFile(self,wikiUser):
        '''
        call back
        '''
        pageContent=self.getContent()
        ignoreExists=True
        wikipush=WikiPush(fromWikiId=None,toWikiId=wikiUser,login=True)
        description=f"scanned at {self.timestampStr}"  
        msg=f"uploading {self.pageTitle} ({self.fileName}) to {wikiUser} ... " 
        files=[self.scannedFile]
        wikipush.upload(files,force=ignoreExists)
        pageToBeEdited=wikipush.toWiki.getPage(self.pageTitle)
        if (not pageToBeEdited.exists) or ignoreExists:
            pageToBeEdited.edit(pageContent,description)
            wikipush.log(msg+"✅")
            pass
            
    def getContent(self):
        '''
        get my content
        
        Return:
            str: the content of the wikipage
        '''
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
        
