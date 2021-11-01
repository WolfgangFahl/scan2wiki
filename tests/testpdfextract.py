'''
Created on 21.03.2021

@author: wf
'''
import unittest
from scan.uploadentry import UploadEntry
from os import path,listdir
from tests.basetest import BaseTest
        
class TestPDFExtract(BaseTest):
    '''
    test PDF text extraction
    '''

    def setUp(self):
        BaseTest.setUp(self)
        self.testdata = "%s/data" % path.abspath(path.dirname(__file__))
        pass


    def testPDFExtract(self):
        '''
        test the PDF extraction
        '''
        expected={
            "2016_01_17_09_32_49.jpg": None,
            "2015_11_14_17_53_37.pdf":["Requirements","Engineering","Prüfung"],
            "2021/2021_10_20_15_51_33.pdf":["ALDI SÜD"],
            "2021/2021_11_01_13_03_50.pdf":["Universal Declaration of Human Rights"]
        }
        for testFile in expected.keys():
            uploadEntry=UploadEntry(self.testdata,testFile)
            pdfText=uploadEntry.ocrText
            if testFile in expected:
                if self.debug:
                    print(str(uploadEntry))
                    print(pdfText)
                exContentList=expected[testFile]
                if exContentList is None:
                    self.assertIsNone(pdfText)
                else:
                    for exContent in exContentList:
                        self.assertTrue(exContent in pdfText,testFile)
            
           
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()