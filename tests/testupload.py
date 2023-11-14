"""
Created on 2021-03-21

@author: wf
"""
from os import listdir
from scan.dms import Document
from ngwidgets.basetest import Basetest
from scan.scan_webserver import ScanWebServer

class TestUpload(Basetest):
    """
    test uploading to a mediawiki
    """

    def setUp(self):
        Basetest.setUp(self)
        self.testdata = ScanWebServer.examples_path()

    def testUpload(self):
        # don't test this in public CIs e.g. travis, github
        if self.inPublicCI():
            return
        wikiId = "test2"
        for testFile in listdir(self.testdata):
            if testFile.endswith(".pdf"):
                uploadEntry = Document()
                uploadEntry.fromFile(self.testdata, testFile, withOcr=True, local=True)
                uploadEntry.uploadFile(wikiId)
        pass
