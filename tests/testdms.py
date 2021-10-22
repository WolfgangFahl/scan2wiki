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
        am=ArchiveManager(mode='json')
        for archiveRecord in Archive.getSamples():
            archive=Archive()
            archive.fromDict(archiveRecord)
            am.getList().append(archive)
        jsonStr=am.toJSON(limitToSampleFields=True)
        print(jsonStr)
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()