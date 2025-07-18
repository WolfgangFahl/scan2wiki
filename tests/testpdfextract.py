"""
Created on 21.03.2021

@author: wf
"""

from ngwidgets.basetest import Basetest

from scan.dms import Document
from scan.pdf import PDFExtractor
from scan.scan_webserver import ScanSolution


class TestPDFExtract(Basetest):
    """
    test PDF text extraction
    """

    def setUp(self):
        Basetest.setUp(self)
        self.testdata = ScanSolution.examples_path()
        self.debug = False
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
            doc.fromFile(self.testdata, testFile, withOcr=True, local=True)
            pdfText = doc.getOcrText()
            pdf_text_extracted = PDFExtractor.getPDFText(doc.fullpath, useCache=False)
            if self.debug:
                print(str(doc))
                print(pdfText)
            exContentList = expected[testFile]
            if exContentList is None:
                self.assertIsNone(pdfText)
            else:
                for exContent in exContentList:
                    self.assertTrue(exContent in pdfText, testFile)
                self.assertEqual(pdfText, pdf_text_extracted)

        pass
