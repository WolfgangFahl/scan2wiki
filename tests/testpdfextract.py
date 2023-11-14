"""
Created on 21.03.2021

@author: wf
"""
from scan.dms import Document
from ngwidgets.basetest import Basetest
from scan.scan_webserver import ScanWebServer

class TestPDFExtract(Basetest):
    """
    test PDF text extraction
    """

    def setUp(self):
        Basetest.setUp(self)
        self.testdata = ScanWebServer.examples_path()
        #self.debug=True
        pass

    def testPDFExtract(self):
        """
        test the PDF extraction
        """
        expected = {
            "2016_01_17_09_32_49.jpg": None,
            "2015_11_14_17_53_37.pdf": ["Requirements", "Engineering", "Prüfung"],
            "2021/2021_10_20_15_51_33.pdf": ["ALDI SÜD"],
            "2021/2021_11_01_13_03_50.pdf": ["Universal Declaration of Human Rights"],
        }
        for testFile in expected.keys():
            doc = Document()
            doc.fromFile(self.testdata, testFile, withOcr=True,local=True)
            pdfText = doc.getOcrText()
            if testFile in expected:
                if self.debug:
                    print(str(doc))
                    print(pdfText)
                exContentList = expected[testFile]
                if exContentList is None:
                    self.assertIsNone(pdfText)
                else:
                    for exContent in exContentList:
                        self.assertTrue(exContent in pdfText, testFile)

        pass
