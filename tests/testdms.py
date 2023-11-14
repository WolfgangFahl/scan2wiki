"""
Created on 2021-10-21

@author: wf
"""
from ngwidgets.basetest import Basetest
from scan.dms import Archive, ArchiveManager, FolderManager, DocumentManager
from scan.profiler import Profiler

class TestDMS(Basetest):
    """
    test document management system handling
    """

    def setUp(self):
        """
        setup this test
        """
        Basetest.setUp(self)
        if self.inPublicCI():
            am = self.getSampleArchiveManager()
            am.store()

    def getSampleArchiveManager(self):
        """
        get an archive manager based on the samples
        """
        am = ArchiveManager(mode="json")
        for archiveRecord in Archive.getSamples():
            archive = Archive()
            archive.fromDict(archiveRecord)
            am.getList().append(archive)
        return am

    def testArchive(self):
        """
        test the Archive concept
        """
        am = self.getSampleArchiveManager()
        jsonStr = am.toJSON(limitToSampleFields=True)
        expectedNameValues = [
            '''"name": "media"''',
            '''"server": "media.bitplan.com"''',
            '''"url": "http://media.bitplan.com"''',
            '''"wikiid": "media"''',
        ]
        debug = self.debug
        if debug:
            print(jsonStr)
        for expected in expectedNameValues:
            self.assertTrue(expected in jsonStr)
        am2 = ArchiveManager.getInstance()
        archives = am2.archives
        self.assertTrue(len(archives) > 0)
        pass

    def testFolders(self):
        """
        test folder handling
        """
        am = self.getSampleArchiveManager()
        archivesByUrl, _dup = am.getLookup("url")
        archives = [archivesByUrl["http://wiki.bitplan.com"]]
        expected = {}
        expected["wiki"] = 0
        if not self.inPublicCI():
            archives = []
            amb = ArchiveManager.getInstance(mode="json")
            amb.fromCache()
            for archive in amb.archives:
                if not hasattr(archive, "wikiid"):
                    archives.append(archive)
            expected["bitplan-scan"] = 320
            expected["fahl-scan"] = 190
        for archive in archives:
            store = self.inPublicCI()
            store = True
            if store:
                # prepare managers
                FolderManager.getInstance()
                DocumentManager.getInstance()
            am.addFilesAndFoldersForArchive(archive, store=store)

            # if not self.inPublicCI():
            #    self.assertTrue(folderCount>=expected[archive.name])
            # foldersByName,_dup=fms.getLookup("path")
            # folder=foldersByName["/bitplan/scan/2019"]
            # if self.debug:
            #        print (folder.toJSON())

    def testOCRText(self):
        """
        test OCR text access
        """
        dm = DocumentManager.getInstance()
        doc_count = len(dm.documents)
        debug=True
        if debug:
            print(doc_count)
        i_list = []
        if doc_count>20:
            i_list.extend(range(4, 11))
            i_list.extend(range(13, 14))
            i_list.extend(range(17, 20))
        for i in i_list:
            doc = dm.documents[i]
            print(f"{i+1:4}:{doc.name} ...")
            profiler = Profiler(msg="OCR Text reading")
            profiler.start()
            ocr_text = doc.getOcrText()
            _elapsed, elapsedMessage = profiler.time()
            print(f"... {len(ocr_text):6} {elapsedMessage}")

    def testUnicodeDammit(self):
        """ """
        if not self.inPublicCI():
            from bs4 import UnicodeDammit

            with open(
                "/Volumes/bitplan/scan/2007/.ocr/IT-Management_2007-05_Automatisierte_Effizienz_p001.txt",
                "rb",
            ) as file:
                content = file.read()
                suggestion = UnicodeDammit(content)
                encoding = suggestion.original_encoding
                print(encoding)
