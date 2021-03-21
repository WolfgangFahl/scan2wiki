'''
Created on 21.03.2021

@author: wf
'''
import unittest
import getpass

class TestUpload(unittest.TestCase):


    def setUp(self):
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
    
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()