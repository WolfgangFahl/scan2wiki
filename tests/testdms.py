'''
Created on 22.10.2021

@author: wf
'''
import unittest
from tests.basetest import BaseTest
from scan.dms import Archive,ArchiveManager

class TestDMS(BaseTest):
    '''
    test document management system handling
    '''

    def testArchive(self):
        '''
        test the Archive concept
        '''
        am=ArchiveManager(mode='json')
        for archiveRecord in Archive.getSamples():
            archive=Archive()
            archive.fromDict(archiveRecord)
            am.getList().append(archive)
        jsonStr=am.toJSON(limitToSampleFields=True)
        expected='''{
    "archives": [
        {
            "name": "media",
            "server": "media.bitplan.com",
            "url": "http://media.bitplan.com",
            "wikiid": "media"
        }
    ]
}'''
        if self.debug:
            print(jsonStr)
        self.assertEqual(expected,jsonStr)    
        if self.isInPublicCI():
            am.store()
        am2=ArchiveManager.getInstance()
        archives=am2.archives
        self.assertTrue(len(archives)>0)
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()