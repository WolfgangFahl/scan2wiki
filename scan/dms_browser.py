'''
Created on 2022-11-15

@author: wf
'''
import os
from jpcore.compat import Compatibility;Compatibility(0,11,1)
from jpcore.justpy_config import JpConfig
script_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.dirname(script_dir)+"/static"
JpConfig.set("STATIC_DIRECTORY",static_dir)
JpConfig.setup()

from jpwidgets.bt5widgets import App
import sys

class Version(object):
    '''
    Version handling for bootstrap5 example
    '''
    name="DMS Browser"
    version='0.0.1'
    date = '2022-11-15'
    updated = '2022-11-15'
    description='Document Management System Browser'
    authors='Wolfgang Fahl'
    license=f'''Copyright 2022 contributors. All rights reserved.
  Licensed under the Apache License 2.0
  http://www.apache.org/licenses/LICENSE-2.0
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.'''
    longDescription=f"""{name} version {version}
{description}
  Created by {authors} on {date} last updated {updated}"""

class DMS_Browser(App):
    '''
    Document Management System browser
    '''
    
    def __init__(self,version):
        '''
        Constructor
        
        Args:
            version(Version): the version info for the app
        '''
        App.__init__(self, version)
        self.addMenuLink(text='Home',icon='home', href="/")
        self.addMenuLink(text='github',icon='github', href="https://github.com/WolfgangFahl/scan2wiki")
        self.addMenuLink(text='Documentation',icon='file-document',href="https://wiki.bitplan.com/index.php/PyJustpyWidgets")
        self.addMenuLink(text='Source',icon='file-code',href="https://github.com/WolfgangFahl/pyJustpyWidgets/blob/main/jpdemo/jpexamples/jpTableDemo.py")
        
    async def content(self):
        '''
        show the content
        '''
        head_html="""<link rel="stylesheet" href="/static/css/md_style_indigo.css">"""
        wp=self.getWp(head_html)
        return wp
    
DEBUG = 1
if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-d")
    app=DMS_Browser(Version)
    sys.exit(app.mainInstance())