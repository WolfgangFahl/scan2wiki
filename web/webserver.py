'''
Created on 2021-03-26

@author: wf
'''

from fb4.app import AppWrap
from flask import render_template
import sys

class Scan2WikiServer(AppWrap):
    ''' 
    Wrapper for Flask Web Application 
    '''
    
    def __init__(self, host='0.0.0.0', port=8334, debug=False):
        '''
        constructor
        '''
        super().__init__(host=host,port=port,debug=debug)
        
        @self.app.route('/')
        def homeroute():
            return self.home()
        
    def home(self):
        template="index.html"
        title="Scan2Wiki"
        html=render_template(template, title=title)
        return html
        
    @staticmethod
    def startServer(sysargs,dorun=True):
        server=Scan2WikiServer()
        parser=server.getParser(description="Scan2Wiki Server")
        args=parser.parse_args(sysargs)
        server.optionalDebug(args)
        if dorun:
            server.run(args)
        return server
        
        
if __name__ == '__main__':
    sysargs=sys.argv[1:]
    server=Scan2WikiServer.startServer(sysargs)
    
    