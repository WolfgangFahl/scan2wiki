'''
Created on 2021-03-26

@author: wf
'''

from fb4.app import AppWrap
from flask import render_template, url_for
from fb4.widgets import  Menu, MenuItem, Link
from wtforms import validators
from wtforms import  SelectField,  TextField, SubmitField,  FileField
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from pathlib import Path
from datetime import datetime
import sys
import os


# https://stackoverflow.com/a/60157748/1497139
import werkzeug
from flask.helpers import send_from_directory
werkzeug.cached_property = werkzeug.utils.cached_property
from flask_autoindex import AutoIndex
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
            fullpath=f"{self.scandir}/{path}"
            ftime=datetime.fromtimestamp(os.path.getmtime(fullpath))
            ftimestr=ftime.strftime("%Y-%m-%d %H:%M:%S")
            size=os.path.getsize(fullpath)
            fileLink=Link(self.basedUrl(url_for("files",path=path)),path)
            scanFile={
                'name': fileLink,
                'lastModified': ftimestr,
                'size': size
                
            }
            scanFiles.append(scanFile)
        lodKeys=["name","lastModified","size"]    
        tableHeaders=lodKeys
        return scanFiles,lodKeys,tableHeaders
    
    def files(self,path):
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
    
        
if __name__ == '__main__':
    sysargs=sys.argv[1:]
    server=Scan2WikiServer.startServer(sysargs)
    
    