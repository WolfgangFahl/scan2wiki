'''
Created on 22.10.2021

@author: wf
'''
import unittest
from tests.basetest import BaseTest
from scan.dms import Archive,ArchiveManager,FolderManager,DocumentManager

class TestDMS(BaseTest):
    '''
    test document management system handling
    '''
    
    def setUp(self):
        '''
        setup this test
        '''
        BaseTest.setUp(self)
        if self.isInPublicCI():
            am=self.getSampleArchiveManager()
            am.store()
        
    def getSampleArchiveManager(self):
        '''
        get an archive manager based on the samples
        '''
        am=ArchiveManager(mode='json')
        for archiveRecord in Archive.getSamples():
            archive=Archive()
            archive.fromDict(archiveRecord)
            am.getList().append(archive)
        return am

    def testArchive(self):
        '''
        test the Archive concept
        '''
        am=self.getSampleArchiveManager()
        jsonStr=am.toJSON(limitToSampleFields=True)
        expected='''{
            "name": "media",
            "server": "media.bitplan.com",
            "url": "http://media.bitplan.com",
            "wikiid": "media"
        }'''
        if self.debug:
            print(jsonStr)
        self.assertTrue(expected in jsonStr)    
        am2=ArchiveManager.getInstance()
        archives=am2.archives
        self.assertTrue(len(archives)>0)
        pass
    
    def testFolders(self):
        '''
        test folder handling
        '''
        am=self.getSampleArchiveManager()
        archivesByUrl,_dup=am.getLookup("url")
        archives=[archivesByUrl["http://wiki.bitplan.com"]]
        expected={}
        expected["wiki"]=0
        if not self.inPublicCI():
            amb=ArchiveManager.getInstance(mode='json')
            for archive in amb.archives:
                if not hasattr(archive,"wikiid"):
                    archives.append(archive)
            expected["bitplan-scan"]=320
            expected["fahl-scan"]=190
        self.debug=True
        folders=[]
        for archive in archives:
            msg=f"getting folders for {archive.name}"
            if self.debug:
                print(msg)
            afoldersByPath,documentList=(archive.getFoldersAndDocuments())
            folderCount=len(afoldersByPath)
            msg=f"found {folderCount} folders in {archive.name}"
            folders.extend(afoldersByPath.values())
            if self.debug:
                print(msg)
            self.assertTrue(folderCount>=expected[archive.name])
        if not self.inPublicCI():
            fms=FolderManager(mode='sql')
            fms.folders=folders
            fms.store()
            
            foldersByName,_dup=fms.getLookup("path")
            folder=foldersByName["/bitplan/scan/2019"]
            if self.debug:
                print (folder.toJSON())
                
            dms=DocumentManager(mode='sql')
            dms.documents=documentList
            dms.store()
            

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()