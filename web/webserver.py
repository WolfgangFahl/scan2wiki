'''
Created on 2021-03-26

@author: wf
'''

from fb4.app import AppWrap
from flask import render_template
from fb4.widgets import DropDownMenu, Menu, MenuItem, Link
from wtforms import validators
from wtforms.fields.html5 import EmailField
from wtforms import  SelectField,  TextField, SubmitField,  TextAreaField
from flask_wtf import FlaskForm
import sys
import os
# https://stackoverflow.com/a/60157748/1497139
import werkzeug
werkzeug.cached_property = werkzeug.utils.cached_property
from flask_autoindex import AutoIndex


class Scan2WikiServer(AppWrap):
    ''' 
    Wrapper for Flask Web Application 
    '''
    
    def __init__(self, host='0.0.0.0', port=8334, debug=False):
        '''
        constructor
        '''
        scriptdir = os.path.dirname(os.path.abspath(__file__))
        template_folder=scriptdir + '/../templates'
        super().__init__(host=host,port=port,debug=debug,template_folder=template_folder)
        self.scandir="/Users/wf/Pictures/scan"
        
        @self.app.route('/')
        def homeroute():
            return self.home()
        
        @self.app.route('/files')
        @self.app.route('/files/<path:path>')
        def autoindex(path='.'):
            return self.files(path)
        
        @self.app.route('/scandir')
        def showScanDirectory():
            return self.watchDir()
        
    def home(self):
        template="index.html"
        title="Scan2Wiki"
        
        html=render_template(template, title=title, menu=self.getMenu())
        return html
    
    def files(self,path):
        files_index = AutoIndex(self.app, self.scandir, add_url_rules=False)
        return files_index.render_autoindex(path)

    
    def watchDir(self):
        title="Scan2Wiki"
        template="watch.html"
        watchForm=WatchForm()
        html=render_template(template, title=title, menu=self.getMenu(),watchForm=watchForm)
        return html
    
    def getMenu(self):
        menu=Menu()
        menu.addItem(MenuItem("/scandir","Scan-Directory"))
        menu.addItem(MenuItem("/files","Scans"))
        menu.addItem(MenuItem("/imprint","Imprint"))
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
    name = TextField('Name',[validators.DataRequired()],render_kw={'placeholder': 'Some name'})
    submit = SubmitField()
    
        
if __name__ == '__main__':
    sysargs=sys.argv[1:]
    server=Scan2WikiServer.startServer(sysargs)
    
    