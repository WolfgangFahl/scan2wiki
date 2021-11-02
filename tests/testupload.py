'''
Created on 21.03.2021

@author: wf
'''
import unittest
from os import path,listdir
from scan.dms import Document
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
        wikiId="test2"
        for testFile in listdir(self.testdata):
            if testFile.endswith(".pdf"):
                uploadEntry=Document()
                uploadEntry.fromFile(self.testdata,testFile,withOcr=True)
                uploadEntry.uploadFile(wikiId)
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()