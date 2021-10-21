'''
Created on 2021-03-26

@author: wf
'''

from fb4.app import AppWrap
from flask import render_template, url_for
from fb4.widgets import  Menu, MenuItem, Link,Widget
from wtforms import validators
from wtforms.widgets import HiddenInput
from wtforms import  SelectField,  StringField, TextAreaField, SubmitField,  FileField
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from pathlib import Path
from datetime import datetime
from scan.uploadentry import UploadEntry
from wikibot.wikiuser import WikiUser
import sys
import os

# https://stackoverflow.com/a/60157748/1497139
import werkzeug
from flask.helpers import send_from_directory
werkzeug.cached_property = werkzeug.utils.cached_property
from scan.scan2wiki import Scan2Wiki

class Scan2WikiServer(AppWrap):
    ''' 
    Web app for scanning documents to a wiki
    '''
    
    def __init__(self, host='0.0.0.0', port=8334, debug=False):
        '''
        constructor
        '''
        scriptdir = os.path.dirname(os.path.abspath(__file__))
        template_folder=scriptdir + '/../templates'
        super().__init__(host=host,port=port,debug=debug,template_folder=template_folder)
        self.scandir=Scan2Wiki.getScanDir()
        self.wikiUsers=WikiUser.getWikiUsers()

        
        @self.app.route('/')
        def homeroute():
            return self.home()
        
        @self.app.route('/files')
        @self.app.route('/files/<path:path>')
        def files(path='.'):
            return self.files(path)
        
        @self.app.route('/scandir')
        def showScanDirectory():
            return self.watchDir()
        
        @self.app.route('/delete/<path:path>')
        def delete(path=None):
            return self.delete(path)
        
        @self.app.route('/upload/<path:path>',methods=['GET', 'POST'])
        def upload(path=None):
            return self.upload(path)
        
    def home(self):
        '''
        show the main page
        '''
        template="index.html"
        title="Scan2Wiki"
        
        html=render_template(template, title=title, menu=self.getMenuList())
        return html
    
    def getScanFiles(self):
        '''
        '''
        scanFiles=[]
        for path in os.listdir(self.scandir):
            fullpath=self.getFullPath(path)
            ftime=datetime.fromtimestamp(os.path.getmtime(fullpath))
            ftimestr=ftime.strftime("%Y-%m-%d %H:%M:%S")
            size=os.path.getsize(fullpath)
            fileLink=Link(self.basedUrl(url_for("files",path=path)),path)
            scanFile={
                'name': fileLink,
                'lastModified': ftimestr,
                'size': size,
                'delete': Link(self.basedUrl(url_for('delete',path=path)),'❌'),
                'upload': Link(self.basedUrl(url_for('upload',path=path)),'⇧')
                
            }
            scanFiles.append(scanFile)
        lodKeys=["name","lastModified","size","delete","upload"]    
        tableHeaders=lodKeys
        return scanFiles,lodKeys,tableHeaders
    
    def getFullPath(self,path):
        path=secure_filename(path)
        fullpath=f"{self.scandir}/{path}"
        return fullpath
    
    def delete(self,path):
        '''
        Args:
            path(str): the file to delete
        '''
        fullpath=self.getFullPath(path)
        os.remove(fullpath)
        return self.files()
        
    
    def files(self,path="."):
        '''
        show the files in the given path
        
        Args:
            path(str): the path to render
        '''
        fullpath=f"{self.scandir}/{path}"
        if os.path.isdir(fullpath):
            # https://stackoverflow.com/questions/57073384/how-to-add-flask-autoindex-in-an-html-page
            # return files_index.render_autoindex(path,template="scans.html")
            dictList,lodKeys,tableHeaders=self.getScanFiles()
            return render_template('scans.html',title="Scans",menu=self.getMenuList(),dictList=dictList,lodKeys=lodKeys,tableHeaders=tableHeaders)
        else:
            return send_from_directory(self.scandir,path)

    
    def upload(self,path):
        '''
        upload a single file to a wiki
        
        Args:
            path(str): the path to render
        '''
        title='upload'
        template="upload.html"
        uploadForm=UploadForm()
        if uploadForm.validate_on_submit():
            uploadEntry=uploadForm.toUploadEntry(self.scandir)
            uploadEntry.uploadFile(uploadForm.wikiUser.data)
        else:
            uploadEntry=UploadEntry(self.scandir,path)
            uploadForm.fromUploadEntry(uploadEntry)
            pass
        uploadForm.update()
        html=render_template(template, title=title, menu=self.getMenuList(),uploadForm=uploadForm)
        return html
        
    def watchDir(self):
        title="Scan2Wiki"
        template="watch.html"
        watchForm=WatchForm()
        if watchForm.validate_on_submit():
            filename = secure_filename(watchForm.file.data.filename)
            pass
        html=render_template(template, title=title, menu=self.getMenuList(),watchForm=watchForm)
        return html
    
    def getMenuList(self):
        '''
        set up the menu for this application
        '''
        menu=Menu()
        menu.addItem(MenuItem("/scandir","Scan-Directory"))
        menu.addItem(MenuItem("/files","Scans"))
        menu.addItem(MenuItem('http://wiki.bitplan.com/index.php/scan2wiki',"Docs")),
        menu.addItem(MenuItem('https://github.com/WolfgangFahl/scan2wiki','github'))
        return menu
        
    @staticmethod
    def startServer(sysargs,dorun=True):
        server=Scan2WikiServer()
        parser=server.getParser(description="Scan2Wiki Server")
        args=parser.parse_args(sysargs)
        server.optionalDebug(args)
        if dorun:
            server.run(args)
        return server
        
class WatchForm(FlaskForm):
    """
    Watch directory form
    """
    home = str(Path.home())
    scandirField = FileField('Scandir',[validators.DataRequired()],render_kw={'placeholder': f'{home}'})
    submit = SubmitField()
    
class WidgetWrapper(HiddenInput):
    '''
    wraps an fb4 widget
    '''
    def __call__(self, field, **kwargs):
        if field.data and isinstance(field.data,Widget):
            html=field.data.render()
        else:
            html=""
        return html
    
class UploadForm(FlaskForm):
    '''
    upload form
    '''
    submit=SubmitField('upload')
    pageTitle=StringField('pagetitle',[validators.DataRequired()])
    pageLink=StringField('pagelink',widget=WidgetWrapper())
    # https://stackoverflow.com/q/21217475/1497139
    wikiUser=SelectField('Wiki', choices=[('fahl', 'fahl.bitplan.com'),('media', 'media.bitplan.com'),('scan', 'scan.bitplan.com'), ('test', 'test.bitplan.com') ])
    scannedFile=StringField('scannedFile')
    categories=StringField('categories')
    topic=StringField('topic')
    # https://stackoverflow.com/a/23256596/1497139
    ocrText=TextAreaField('Text', render_kw={"rows": 15, "cols": 60})
    
    def update(self):
        pageTitle=f"{self.pageTitle.data}"
        wikiLink=f"http://{self.wikiUser.data}.bitplan.com/index.php/{pageTitle}"
        self.pageLink.data=Link(wikiLink,pageTitle)
 
    def fromUploadEntry(self,u:UploadEntry):
        '''
        fill my from from the given uploadEntry
        '''
        self.scannedFile.data=u.fileName
        self.wikiUser.data=u.wikiUser
        self.pageTitle.data=u.pageTitle
        self.topic.data=u.topic
        self.categories.data=u.categories
        self.ocrText.data=u.getPDFText()
        
    def toUploadEntry(self,scandir):
        '''
        convert me to an upload entry
        
        Return:
            UploadEntry: the upload entry to use
        '''
        u=UploadEntry(scandir,self.scannedFile.data)
        u.wikiUser=self.wikiUser.data
        u.pageTitle=self.pageTitle.data
        u.topic=self.topic.data
        u.categories=self.categories.data
        u.ocrText=self.ocrText.data
        return u

def main():
    sysargs=sys.argv[1:]
    server=Scan2WikiServer.startServer(sysargs)
        
if __name__ == '__main__':
    sys.exit(main()) 
    
    