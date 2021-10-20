'''
Created on 2021-03-21

@author: wf
'''
import os
os.environ["PYWIKIBOT_NO_USER_CONFIG"]="2"
import sys
from pathlib import Path
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from scan.wikiuploaddialog import WikiUploadDialog
from wikibot.wikiuser import WikiUser
from wikibot.wikipush import WikiPush
from scan.folderwatcher import Watcher

class Scan2Wiki(object):
    '''
    scan documents to wikis
    '''

    def __init__(self,debug=False):
        '''
        Constructor
        
        Args:
            debug(bool): True if debugging should be switched on
        '''
        self.debug=debug
        
    @staticmethod
    def getScanDir():
        '''
        get the scan/watch directory to be used
        
        Returns:
            str: the path to the scan directory
        '''
        home = str(Path.home())
        scandir=f"{home}/Pictures/scans"
        os.makedirs(scandir, exist_ok=True)
        return scandir
        
    def upload(self,files):
        '''
        upload the given list of files
        
        Args:
            files(list): a list of files (io.TextIoWrapper ...)
        '''
        for file in files:
            print(file)
        wikiUsers=WikiUser.getWikiUsers()    
        uploadDialog= WikiUploadDialog(wikiUsers)
        uploadDialog.show(files,self.uploadFile)
        
    def uploadFile(self,wikiUser,upload):
        '''
        call back
        '''
        pageContent=upload.getContent()
        ignoreExists=True
        wikipush=WikiPush(fromWikiId=None,toWikiId=wikiUser,login=True)
        description=f"scanned at {upload.timestampStr}"  
        msg="uploading %s (%s) to %s ... " % (upload.pageTitle,upload.fileName,wikiUser)
        files=[upload.scannedFile]
        wikipush.upload(files,force=ignoreExists)
        pageToBeEdited=wikipush.toWiki.getPage(upload.pageTitle)
        if (not pageToBeEdited.exists) or ignoreExists:
            pageToBeEdited.edit(pageContent,description)
            wikipush.log(msg+"✅")
            pass
        
__version__ = "0.0.8"
__date__ = '2021-03-21'
__updated__ = '2021-03-22'
DEBUG=False
        
def main(argv=None): # IGNORE:C0111
    '''main program.'''
    if argv is None:
        argv = sys.argv[1:]

    program_name = "scan2wiki"
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = "scan into a Semantic MediaWiki"
    user_name="Wolfgang Fahl"

    program_license = '''%s

  Created by %s on %s.
  Copyright 2021 Wolfgang Fahl. All rights reserved.

  Licensed under the Apache License 2.0
  http://www.apache.org/licenses/LICENSE-2.0

  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

''' % (program_shortdesc,user_name, str(__date__))
    
    try:
        defaultWatchdir=Scan2Wiki.getScanDir()
        parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-w", "--watch", help="directory to watch for incoming files",default=defaultWatchdir)
        parser.add_argument("-d", "--debug", dest="debug",   action="store_true", help="set debug level [default: %(default)s]")
        parser.add_argument('-V', '--version', action='version', version=program_version_message)
        parser.add_argument('--files', nargs='+')
        args = parser.parse_args(argv)
 
        scan2Wiki=Scan2Wiki(args.debug)
        if args.watch:
            watcher=Watcher(args.watch)
            def onFileEvent(file):
                scan2Wiki.upload([file])
            watcher.run(onFileEvent)
        scan2Wiki.upload(args.files)
        
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 1
    except Exception as e:
        if DEBUG:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2
        
if __name__ == "__main__":
    sys.exit(main())
        