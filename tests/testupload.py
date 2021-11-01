'''
Created on 21.03.2021

@author: wf
'''
import unittest
import getpass
from os import path,listdir
from scan.scan2wiki import Scan2Wiki
from scan.uploadentry import UploadEntry
from tests.basetest import BaseTest

class TestUpload(BaseTest):
    '''
    test uploading to a mediawiki
    '''


    def setUp(self):
        BaseTest.setUp(self)
        self.testdata = "%s/data" % path.abspath(path.dirname(__file__))
        pass


    def testUpload(self):
        # don't test this in public CIs e.g. travis, github
        if self.inPublicCI(): return
        scan2Wiki=Scan2Wiki(self.debug)
        for testFile in listdir(self.testdata):
            if testFile.endswith(".pdf"):
                uploadEntry=UploadEntry(self.testdata,testFile)
                scan2Wiki.uploadFile("test2", uploadEntry)    
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()