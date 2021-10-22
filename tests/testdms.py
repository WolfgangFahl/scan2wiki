'''
Created on 22.10.2021

@author: wf
'''
import unittest
from tests.basetest import BaseTest
from scan.dms import Archive,ArchiveManager, Folder, FolderManager

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
        fm=FolderManager(mode="json")
        if not self.inPublicCI():
            archive=Archive()
            archive.name="bitplan-scan"
            archive.server="capri.bitplan.com"
            archive.url="http://capri.bitplan.com/bitplan/scan/"
            archives.append(archive)
            expected["bitplan-scan"]=10
        for archive in archives:
            folders=archive.getFolders()
            folderCount=len(folders)
            msg=f"found {folderCount} folders in {archive.name}"
            self.debug=True
            if self.debug:
                print(msg)
            self.assertTrue(folderCount>=expected[archive.name])
        if not self.inPublicCI():
            fm.folders=folders
            fm.store()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()