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
from datetime import datetime, timedelta
from scan.uploadentry import UploadEntry
from scan.profiler import Profiler
from wikibot.wikiuser import WikiUser
from scan.dms import ArchiveManager, FolderManager, DocumentManager
import sys
import os
from fb4.sse_bp import SSE_BluePrint

# https://stackoverflow.com/a/60157748/1497139
import werkzeug
from flask.helpers import send_from_directory
from lodstorage.jsonable import JSONAble
from lodstorage.lod import LOD
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
        # https://flask.palletsprojects.com/en/2.0.x/config/#EXPLAIN_TEMPLATE_LOADING
        self.app.config['EXPLAIN_TEMPLATE_LOADING']=True
        self.sseBluePrint=SSE_BluePrint(self.app,'sse')
        self.scandir=Scan2Wiki.getScanDir()
        self.wikiUsers=WikiUser.getWikiUsers()
        self.am=ArchiveManager.getInstance()
        self.archivesByName,_dup=self.am.getLookup("name")

        
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
        
        @self.app.route('/archives/getFoldersAndFiles/<name>')
        def getFoldersAndFiles(name:str):
            return self.getFoldersAndFiles(name)
        
        @self.app.route('/archives')
        def showArchives():
            return self.showArchives()
        
        @self.app.route('/archive/<name>')
        def showArchive(name:str):
            return self.showArchive(name)
        
        @self.app.route('/folders')
        def showFolders():
            return self.showFolders()
        
        @self.app.route('/documents')
        def showDocuments():
            return self.showDocuments()
        
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
            try: 
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
            except Exception as ex:
                msg=f"error {str(ex)} for {path}"
                print(msg)
        lodKeys=["name","lastModified","size","delete","upload"]    
        tableHeaders=lodKeys
        return scanFiles,lodKeys,tableHeaders
    
    def getFullPath(self,path):
        '''
        get the full path for the given path
        
        Args:
            path(str): the path
        
        Return:
            str: the full path
        '''
        #path=secure_filename(path)
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
            return render_template('datatable.html',title="Scans",menu=self.getMenuList(),dictList=dictList,lodKeys=lodKeys,tableHeaders=tableHeaders)
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
        else:
            watchForm.scandirField.data=self.scandir
            pass
        html=render_template(template, title=title, menu=self.getMenuList(),watchForm=watchForm)
        return html
    
    def getMenuList(self):
        '''
        set up the menu for this application
        '''
        menu=Menu()
        menu.addItem(MenuItem("/archives","Archives"))
        menu.addItem(MenuItem("/folders","Folders"))
        menu.addItem(MenuItem("/documents","Documents"))
        menu.addItem(MenuItem("/scandir","Scan-Directory"))
        menu.addItem(MenuItem("/files","Scans"))
        menu.addItem(MenuItem('http://wiki.bitplan.com/index.php/scan2wiki',"Docs")),
        menu.addItem(MenuItem('https://github.com/WolfgangFahl/scan2wiki','github'))
        return menu
    
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
                record[name]=Link(lurl,title)
                
    def showArchives(self):
        '''
        show the list of archives
        '''
        return self.showEntityManager(self.am,self.archiveRowHandler,self.archiveLodKeyHandler)
    
    def archiveLodKeyHandler(self,lodkeys):
        lodkeys.append("🔄")
        
    def archiveRowHandler(self,row):
        '''
        handle a row in the showArchive table view
        '''
        name=row['name']
        row['🔄']=Link(self.basedUrl(url_for("getFoldersAndFiles",name=name)),'🔄')
        self.defaultRowHandler(row)
        row['name']=Link(self.basedUrl(url_for("showArchive",name=name)),name)
    
    def getFoldersAndFiles(self,name:str):
        '''
        get folders and files for the archive with the given name
        
        Args:
            name(str): the name of the archive to get the folders and files for
        '''
        if name in self.archivesByName:
            archive=self.archivesByName[name]
            msg=f"getting folders and files for {name}"
            pd=ProgressDisplayer(self,msg)
            title="Archive - get Folders and Documents"
            debug=True
            startMsg=pd.start(ArchiveManager.addFilesAndFoldersForArchive,kwargs={"archive":archive, "store":True, "debug":debug})
            return render_template("progress.html",title=title,menu=self.getMenuList(),msg=startMsg)
        else:
            return f"Archive with  name {name} not found", 400
    
    def showArchive(self,name):
        '''
        show the archive with the given name
        '''
        if name in self.archivesByName:
            return self.showEntity(self.archivesByName[name])
        else:
            return f"Archive with  name {name} not found", 400
        
    def showFolders(self):
        '''
        show the list of folders
        '''
        fm=FolderManager.getInstance()
        return self.showEntityManager(fm)
    
    def showDocuments(self):
        '''
        show the list of documents
        '''
        dm=DocumentManager.getInstance()
        return self.showEntityManager(dm)
    
    def defaultRowHandler(self,row):
        self.linkColumn('url',row, formatWith="%s")
        
    def showEntity(self,entity:JSONAble):
        '''
        show the given entity
        '''
        title=entity.__class__.__name__
        samples=entity.getJsonTypeSamples()
        sampleFields = LOD.getFields(samples)
        dictList=[]
        for key in sampleFields:
            if hasattr(entity,key):
                value=getattr(entity,key)
            else:
                value="-"
            keyValue={"key": key, 'value':value}
            dictList.append(keyValue)
        lodKeys=["key","value"]
        tableHeaders=lodKeys
        return render_template('datatable.html',title=title,menu=self.getMenuList(),dictList=dictList,lodKeys=lodKeys,tableHeaders=tableHeaders)
        
    def showEntityManager(self,em,rowHandler=None,lodKeyHandler=None):
        '''
        show the given entity manager
        '''
        records=em.getList()
        firstRecord=records[0]
        lodKeys=list(firstRecord.getJsonTypeSamples()[0].keys())
        if lodKeyHandler is not None:
            lodKeyHandler(lodKeys)
        tableHeaders=lodKeys            
        dictList=[vars(d).copy() for d in records]
        if rowHandler is None:
            rowHandler=self.defaultRowHandler
        for row in dictList:
            rowHandler(row)
        title=em.entityPluralName
        return render_template('datatable.html',title=title,menu=self.getMenuList(),dictList=dictList,lodKeys=lodKeys,tableHeaders=tableHeaders)
        
        
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
    
class ProgressDisplayer:
    '''
    display progress
    '''
    
    def __init__(self,webserver,msg):
        '''
        construct me
        Args:
            webserver(AppWrap): the webserver to work for
            msg(str): the message to display
        '''
        self.webserver=webserver
        self.msg=msg
        
    def start(self,functionToCall,kwargs):
        '''
        start me with the given function to call
        
        Args:
            functionCall(func): the function to be called with a progress display
        Return:
            str: the html response for the initial start
        '''
        self.profiler=Profiler(self.msg)
        startMsg=self.profiler.start()
        # Todo: call background job and start SSE
        now=datetime.now()
        run_date=now+timedelta(seconds=1)
        print(f"scheduling job {functionToCall.__name__} for {run_date.isoformat()}")
        self.webserver.sseBluePrint.scheduler.add_job(functionToCall, 'date',run_date=run_date,kwargs=kwargs)   
        #elapsed,elapsedMessage=self.profiler.time()
        return startMsg
    
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
    '''
    main - command line entry point
    '''
    sysargs=sys.argv[1:]
    _server=Scan2WikiServer.startServer(sysargs)
        
if __name__ == '__main__':
    sys.exit(main()) 
    
    