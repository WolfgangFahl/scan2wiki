'''
Created on 21.03.2021

@author: wf
'''
import unittest
import getpass
from os import path,listdir
from scan.scan2wiki import Scan2Wiki
from scan.uploadentry import UploadEntry

class TestUpload(unittest.TestCase):


    def setUp(self):
        self.testdata = "%s/data" % path.abspath(path.dirname(__file__))
        self.debug=True
        pass

    def inPublicCI(self):
        '''
        are we running in a public Continuous Integration Environment?
        '''
        return getpass.getuser() in [ "travis", "runner" ];

    def tearDown(self):
        pass


    def testUpload(self):
        # don't test this in public CIs e.g. travis, github
        if self.inPublicCI(): return
        scan2Wiki=Scan2Wiki(self.debug)
        for i,testFile in enumerate(listdir(self.testdata)):
            testPath="%s/%s" % (self.testdata,testFile)
            uploadEntry=UploadEntry(i,testPath)
            scan2Wiki.uploadFile("test2", uploadEntry)
    
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()