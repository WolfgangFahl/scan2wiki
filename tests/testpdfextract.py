'''
Created on 21.03.2021

@author: wf
'''
import unittest
from scan.uploadentry import UploadEntry
from os import path,listdir

        
class TestPDFExtract(unittest.TestCase):
    '''
    test PDF text extraction
    '''

    def setUp(self):
        self.testdata = "%s/data" % path.abspath(path.dirname(__file__))
        self.debug=True
        pass


    def tearDown(self):
        pass


    def testPDFExtract(self):
        '''
        test the PDF extraction
        '''
        expected={
            "2016_01_17_09_32_49.jpg": None,
            "2015_11_14_17_53_37.pdf":["Requirements","Engineering","Prüfung"],
            "2021_10_20_15_51_33.pdf":["ALDI SÜD"]
        }
        for testFile in listdir(self.testdata):
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