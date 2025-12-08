"""
Created on 2021-10-21

@author: wf

see http://diagrams.bitplan.com/render/png/0xe1f1d160.png
see http://diagrams.bitplan.com/render/txt/0xe1f1d160.txt

"""

import configparser
import getpass
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from basemkit.yamlable import lod_storable
from bs4 import UnicodeDammit
from lodstorage.sql import SQLDB
from lodstorage.storageconfig import StorageConfig, StoreMode
from wikibot3rd.smw import SMWClient
from wikibot3rd.wikiclient import WikiClient
from wikibot3rd.wikipush import WikiPush
from wikibot3rd.wikiuser import WikiUser

from scan.entity import EntityManager
from scan.logger import Logger
from scan.pdf import PDFExtractor


class Wiki(object):
    """
    Semantic Mediawiki access proxy
    """

    @staticmethod
    def getSMW(wikiId: str):
        """
        get the semantic mediawiki client with the given wikiId

        Args:
            wikiId: the wiki id of the client

        Return:
            SMWClient: the SMWClient with the given id
        """
        wikiClient = Wiki.get(wikiId)
        smw = SMWClient(wikiClient.getSite())
        return smw

    @staticmethod
    def get(wikiId: str):
        """
        get the Wiki Client with the given wikiId

        Args:
            wikiId: the wiki id of the client

        Return:
            WikiClient: the WikiClient with the given id
        """
        Wiki.checkIniFile(wikiId)
        wikiClient = WikiClient.ofWikiId(wikiId)
        wikiClient.login()
        return wikiClient

    @staticmethod
    def inPublicCI():
        """
        are we running in a public Continuous Integration Environment?
        """
        return getpass.getuser() in ["travis", "runner"]

    @staticmethod
    def checkIniFile(wikiId: str, save=None):
        """
        check the ini file for the given wikiId

        Args:
            wikiId(str): the wiki id of the wiki to check
            save(bool): True if a new ini file should be created e.g. for test purposes
                        if not set save is True if we are running in a public continuous integration environment
        """
        if save is None:
            save = Wiki.inPublicCI()
        iniFile = WikiUser.iniFilePath(wikiId)
        if not os.path.isfile(iniFile):
            wikiDict = None
            if wikiId == "wiki":
                wikiDict = {
                    "wikiId": wikiId,
                    "email": "noreply@nouser.com",
                    "url": "https://wiki.bitplan.com",
                    "scriptPath": "/",
                    "version": "MediaWiki 1.35.1",
                }
            if wikiDict is None:
                raise Exception(
                    f"wikiId {wikiId} is not configured in $HOME.mediawiki-japi"
                )
            else:
                wikiUser = WikiUser.ofDict(wikiDict, lenient=True)
                if save:
                    wikiUser.save()
            pass


class DMSStorage:
    """
    Document management system storage configuration
    """

    profile = True
    withShowProgress = True

    @classmethod
    def get_config(cls):
        config = configparser.ConfigParser()
        config.read(os.path.expanduser("~/.dms/config.ini"))
        return config

    @staticmethod
    def fromCache(em: EntityManager):
        """
        initialize the given entity manager from it's cache

        Args:
            em(EntityManager): the entity manager to initialize
        """
        if em.isCached():
            em.fromCache()
        else:
            if em.config.mode is StoreMode.SQL:
                sqlDB = DMSStorage.getSqlDB()
                em.initSQLDB(sqlDB)

    @staticmethod
    def getStorageConfig(debug: bool = False, mode="sql") -> StorageConfig:
        """
        get the storageConfiguration

        Args:
            debug(bool): if True show debug information
            mode(str): sql or json

        Return:
            StorageConfig: the storage configuration to be used
        """
        if mode == "sql":
            config = StorageConfig.getSQL(debug=debug)
        elif mode == "json":
            config = StorageConfig.getJSON()
        elif mode == "jsonpickle":
            config = StorageConfig.getJsonPickle(debug=debug)
        else:
            raise Exception(f"invalid mode {mode}")
        config.cacheDirName = "dms"
        cachedir = config.getCachePath()
        config.profile = DMSStorage.profile
        config.withShowProgress = DMSStorage.withShowProgress
        if mode == "sql":
            config.cacheFile = f"{cachedir}/dms.db"
        return config

    @classmethod
    def getScanDir(cls):
        """
        get the scan/watch directory to be used

        Returns:
            str: the path to the scan directory
        """
        config = cls.get_config()
        scandir = config.get("dms", "scan_inbox")
        return scandir

    @staticmethod
    def getSqlDB():
        """
        get the SQlite database connection
        """
        config = DMSStorage.getStorageConfig(mode="sql")
        # https://stackoverflow.com/a/48234567/1497139
        sqlDB = SQLDB(config.cacheFile, check_same_thread=False)
        return sqlDB

    @staticmethod
    def getDatetime(fullpath: str):
        """
        get the last modification time

        Args:
            fullpath(str): the path to get the datetime for
        """
        timestamp = os.path.getmtime(fullpath)
        ftime = datetime.fromtimestamp(timestamp)
        return ftime

    @staticmethod
    def getTimeStr(fullpath: str):
        """
        get the last modification time

        Args:
            fullpath(str): the path to get the time string for
        """
        ftime = DMSStorage.getDatetime(fullpath)
        ftimestr = ftime.strftime("%Y-%m-%d %H:%M:%S")
        return ftimestr


@lod_storable
class Document:
    """
    a document consist of one or more files in the filesystem
    or a wikipage - the name is the pagetitle
    or the filename without extension

    types then has the list of available file types e.g. "pdf,txt"
    for single page Documents  the document is somewhat redundant to the Page concept

    sqlite document structure
    CREATE TABLE document (
      archiveName TEXT,
      folderPath TEXT,
      fullpath TEXT,
      fileName TEXT,
      basename TEXT,
      timestampStr TEXT,
      pageTitle TEXT,
      categories TEXT,
      topic TEXT,
      url TEXT PRIMARY KEY,
      created TIMESTAMP,
      size INTEGER,
      lastModified TIMESTAMP,
      name TEXT,
      types TEXT,
      ocrText TEXT
    )

    """

    # Archive and path information
    archiveName: str = ""  # e.g. "bitplan-scan"
    folderPath: str = ""  # e.g. "/bitplan/scan/inbox"
    fullpath: str = ""  # e.g. "/Volumes/bitplan/scan/inbox/2025-02-23-13-37-39.pdf"

    # File identification
    fileName: str = ""  # e.g. "2025-02-23-13-37-39.pdf"
    basename: str = ""  # e.g. "2025-02-23-13-37-39" (filename without extension)
    name: str = ""  # e.g. "2025-02-23-13-37-39.pdf"

    # Wiki page information
    pageTitle: str = ""  # e.g. "2025-02-23-13-37-39"
    categories: str = ""  # e.g. "2025" (comma-separated list)
    topic: str = ""  # e.g. "OCRDocument"

    # URL (PRIMARY KEY in SQLite)
    url: str = (
        ""  # e.g. "http://capri.bitplan.com/bitplan/scan/inbox/2025-02-23-13-37-39.pdf"
    )

    # Timestamps
    timestampStr: str = ""  # e.g. "2025-02-23 13:37:40"
    created: Optional[datetime] = None  # e.g. datetime(2025, 2, 23, 13, 37, 40, 378206)
    lastModified: Optional[datetime] = (
        None  # e.g. datetime(2025, 2, 23, 13, 37, 40, 378206)
    )

    # File metadata
    size: int = 0  # e.g. 315358 (bytes)
    types: str = ""  # e.g. "pdf,txt" (comma-separated file types available)

    # Content
    ocrText: Optional[str] = None  # Extracted OCR text from document

    # Internal fields for string representation
    fields: list = field(
        default_factory=lambda: ["archiveName", "folderPath", "fileName"]
    )

    @classmethod
    def getSamples(cls):
        samplesLOD = [
            {
                "archiveName": "bitplan-scan",
                "folderPath": "",
                # TODO: fullpath, filename, basename and timestampStr not needed
                "fullpath": "",
                "fileName": "",
                "basename": "",
                "timestampStr": "",
                "pageTitle": "",
                "categories": "",
                "topic": "",
                "url": "http://capri.bitplan.com/bitplan/scan/2019/",
                "created": datetime(2019, 2, 27, 10, 7, 56),
                "size": 15,
                "lastModified": datetime(2019, 2, 27, 10, 7, 56),
                "name": "2019",
                "types": "pdf",
                "ocrText": "",
            }
        ]
        return samplesLOD

    def __post_init__(self):
        """
        post Constructor logic
        """

    def fromFile(self, folderPath, file, local=False, withOcr=False):
        """
        Args:
            folderPath(str): the directory
            file(str): the file
            withOcr(bool): if true get the OCRText
        """
        self.folderPath = folderPath
        self.name = file
        self.fullpath = f"{Folder.getFullpath(self.folderPath,local)}/{file}"
        self.size = os.path.getsize(self.fullpath)
        self.lastModified = DMSStorage.getDatetime(self.fullpath)
        self.created = self.lastModified
        self.timestampStr = DMSStorage.getTimeStr(self.fullpath)
        self.fileName = Path(self.fullpath).name
        self.basename = Path(self.fullpath).stem
        self.pageTitle = f"{self.basename}"

        self.categories = f"{datetime.now().year}"
        self.topic = "OCRDocument"
        if withOcr:
            self.getOcrText()
        pass

    def __str__(self):
        text = "Upload:"
        delim = ""
        for fieldname in self.fields:
            text += "%s%s=%s" % (delim, fieldname, self.__dict__[fieldname])
            delim = ","
        return text

    def getPDFText(self) -> str:
        """Gets text content from PDF, using cached text file if available.

        First checks for an existing .txt file with the same base name as the PDF.
        If found, returns its contents. Otherwise, extracts text from the PDF file.

        Returns:
            str: The text content of the PDF, or None if not a PDF file.
        """
        # Only process PDF files
        if not self.fullpath.lower().endswith(".pdf"):
            return None

        # Try to extract text using PDFExtractor with caching enabled
        return PDFExtractor.getPDFText(self.fullpath, useCache=True)

    def get_text_head(self, max_lines: int = 9) -> str:
        """
        Get the first few lines of the document's text content.

        Args:
            max_lines: Maximum number of lines to return

        Returns:
            String with the first few lines of text
        """
        if not self.ocrText:
            self.getOcrText()

        if self.ocrText:
            lines = self.ocrText.split("\n")
            return "\n".join(lines[:max_lines] if len(lines) >= max_lines else lines)

        return ""

    def readTextFromFile(self, fileName: str) -> str:
        """
        read text from the given fileName
        """
        try:
            with open(fileName, "r") as textFile:
                return textFile.read()
        except UnicodeDecodeError as _ude:
            # print(f"couldn't decode {fileName}")
            with open(fileName, "rb") as file:
                content = file.read()
                suggestion = UnicodeDammit(content)
                encoding = suggestion.original_encoding
                if encoding is None:
                    encoding = "utf-8"
                try:
                    text = content.decode(encoding)
                except Exception as ex:
                    raise (ex)
                return text

    def readMultiPageOcrText(self, ocrDirectory: str) -> str:
        """
        Read OCR text from multiple page files in the specified directory.

        Args:
            ocrDirectory: Directory containing the page files

        Returns:
            Combined text from all pages, or None if no pages found
        """
        page = 1
        maxPages = 1000
        combinedText = None

        # Check if first page exists
        pageFileName = f"{ocrDirectory}/{self.basename}_p{page:03d}.txt"
        if os.path.isfile(pageFileName):
            pageText = self.readTextFromFile(pageFileName)
            if pageText is not None:
                combinedText = pageText

                # Read remaining pages
                for page in range(2, maxPages):
                    pageFileName = f"{ocrDirectory}/{self.basename}_p{page:03d}.txt"
                    if not os.path.isfile(pageFileName):
                        break
                    nextPage = self.readTextFromFile(pageFileName)
                    if nextPage is not None:
                        combinedText += nextPage

        return combinedText

    def getOcrTextFromPath(self, ocrPath: str, withMultiPage: bool = False) -> str:
        """
        Attempts to read OCR text from a specified directory path.

        Checks for a single-page text file (basename.txt). If not found and
        `withMultiPage` is True, it attempts to read multi-page OCR text.

        Args:
            ocrPath: The directory path (str) to search for OCR text.
            withMultiPage: If True, calls readMultiPageOcrText if the single-page file isn't found.

        Returns:
            The OCR text string if found, otherwise None.
        """
        ocr_text = None
        if os.path.isdir(ocrPath):
            ocrFileName = f"{ocrPath}/{self.basename}.txt"
            if os.path.isfile(ocrFileName):
                ocr_text = self.readTextFromFile(ocrFileName)
            elif withMultiPage:
                ocr_text = self.readMultiPageOcrText(ocrPath)
        return ocr_text

    def getOcrText(self):
        """
        Retrieves the OCR text for the document following a specific search order.

        The search priority is:
        1. Base directory (strict: only single-page OCR).
        2. Hidden .ocr directory (permissive: with multi-page fallback).
        3. Direct extraction from the source file (e.g., PDF).

        Returns:
            The retrieved OCR text string, or None if no text could be found.
        """
        parent = Path(self.fullpath).parent.absolute()
        ocr_text = self.getOcrTextFromPath(parent, withMultiPage=False)
        if ocr_text is None:
            ocr_text = self.getOcrTextFromPath(parent / ".ocr", withMultiPage=True)
        if ocr_text is None:
            ocr_text = self.getPDFText()
        self.ocrText = ocr_text
        return self.ocrText

    def uploadFile(self, wikiId):
        """
        call back
        """
        pageContent = self.getContent()
        ignoreExists = True
        wikipush = WikiPush(fromWikiId=None, toWikiId=wikiId, login=True)
        description = f"scanned at {self.timestampStr}"
        msg = f"uploading {self.pageTitle} ({self.fileName}) to {wikiId} ... "
        files = [self.fullpath]
        wikipush.upload(files, force=ignoreExists)
        pageToBeEdited = wikipush.toWiki.getPage(self.pageTitle)
        if (not pageToBeEdited.exists) or ignoreExists:
            pageToBeEdited.edit(pageContent, description)
            wikipush.log(msg + "✅")
            pass

    def getContent(self):
        """
        get my content

        Return:
            str: the content of the wikipage
        """
        wikicats = ""
        delim = ""
        for category in self.categories.split(","):
            wikicats += "%s[[Category:%s]]" % (delim, category)
            delim = "\n"
        if self.fileName.endswith(".pdf"):
            template = """= pdf pages =
<pdf>%s</pdf>
= text =
<pre>%s</pre>
= pdf =
[[File:%s]]
%s
<headertabs/>
"""
            pageContent = template % (
                self.fileName,
                self.ocrText,
                self.fileName,
                wikicats,
            )
        else:
            template = """[[File:%s]]
%s
<headertabs/>"""
            pageContent = template % (self.fileName, wikicats)

        return pageContent


@lod_storable
class Folder:
    """
    a Folder might be a filesystem folder or a category in a wiki.
    Maps to the SQLite table 'folder'.

    CREATE TABLE folder (
      archiveName TEXT,
      url TEXT,
      fileCount INTEGER,
      lastModified TIMESTAMP,
      created TIMESTAMP,
      name TEXT,
      path TEXT
    )
    """

    # Archive information
    archiveName: str = ""  # e.g. "bitplan-scan"

    # URL (Primary Key in some contexts)
    url: str = ""  # e.g. "http://capri.bitplan.com/bitplan/scan/2019/"

    # Folder/Content metadata
    fileCount: int = 0  # Number of files/documents in the folder
    name: str = ""  # e.g. "2019" (folder name)
    path: str = (
        ""  # e.g. "/bitplan/scan/2019" (absolute path in the filesystem/archive)
    )

    # Timestamps
    lastModified: Optional[datetime] = None  # Last modification timestamp
    created: Optional[datetime] = None  # Creation timestamp

    def __post_init__(self):
        """
        post Constructor logic
        """

    @classmethod
    def getSamples(cls):
        samplesLOD = [
            {
                "archiveName": "bitplan-scan",
                "url": "http://capri.bitplan.com/bitplan/scan/2019/",
                "fileCount": 15,
                "lastModified": datetime(2019, 2, 27, 10, 7, 56),
                "created": datetime(2019, 2, 27, 10, 7, 56),
                "name": "2019",
                "path": "/bitplan/scan/2019",
            }
        ]
        return samplesLOD

    @classmethod
    def getPrefix(cls):
        """
        get the path prefix for this platform (if any)

        Return:
            str: the prefix e.g. /Volumes on Darwin
        """
        if sys.platform == "darwin":
            prefix = f"/Volumes"
        else:
            prefix = ""
        return prefix

    @staticmethod
    def getFullpath(folderPath: str, local: bool = False):
        """
        get the full path as accessible on my platform

        Args:
           folderPath(str): the path of the folder
           local(bool): True if the path is for a local folder

        Return:
            str: the full path of the folder
        """
        if local:
            fullPath = folderPath
        else:
            fullPath = f"{Folder.getPrefix()}{folderPath}"
        return fullPath

    @classmethod
    def getRelpath(cls, folderPath: str) -> str:
        """
        get the relative path as accessible on my platform

        Args:
           folderPath(str): the path of the folder

        Return:
            str: the relative path of the folder
        """
        prefix = Folder.getPrefix()
        if prefix and folderPath.startswith(prefix):
            relbase = folderPath.replace(prefix, "")
        else:
            relbase = folderPath
        return relbase

    def getFiles(self, extension=".pdf"):
        """
        get all files with the given extension

        Args:
            extension(str): the extension to search for

        Return:
            list: the files with the given extension
        """
        files = []
        fullPath = Folder.getFullpath(self.path)
        for file in os.listdir(fullPath):
            if file.endswith(extension) and not file.startswith("._"):
                files.append(file)
        return files

    def getFileDocuments(self):
        """
        get all documents for the OCRDocument files in this folder

        Return:
            list: the list of documents
        """
        files = self.getFiles()
        documents = self.getDocuments(files)
        return documents

    def getDocuments(self, files, withOcr=False, progress_bar=None):
        """
        get the documents for this folder based on the files from my listdir
        progress_bar(Progressbar): a progress bar to track progress

        """
        documentList = []
        msg = f"getting {len(files)} documents for {self.path}"
        Logger.log(msg)
        for file in files:
            try:
                if file.endswith(".pdf"):
                    doc = Document()
                    doc.archiveName = self.archiveName
                    doc.url = f"http://{self.archive.server}{self.path}/{file}"
                    doc.fromFile(self.path, file, withOcr=withOcr)
                    documentList.append(doc)
                    if progress_bar:
                        progress_bar.total += 1
                        progress_bar.update_value(progress_bar.value + 1)
            except Exception as e:
                Logger.logException(e)
        return documentList

    def refreshDocuments(self):
        """
        refresh the documents in this folder
        """
        doclist = self.getFileDocuments()
        for doc in doclist:
            doc.getOcrText()
            pass
        pass


class DocumentManager(EntityManager):
    """
    manager for Documents
    """

    def __init__(self, mode="sql", debug=False):
        """constructor"""
        name = "document"
        entityName = "Document"
        entityPluralName = "documents"
        listName = entityPluralName
        clazz = Document
        tableName = name
        config = DMSStorage.getStorageConfig(mode=mode, debug=debug)
        handleInvalidListTypes = True
        filterInvalidListTypes = True
        primaryKey = "url"
        super().__init__(
            name,
            entityName,
            entityPluralName,
            listName,
            clazz,
            tableName,
            primaryKey,
            config,
            handleInvalidListTypes,
            filterInvalidListTypes,
            debug,
        )

    @staticmethod
    def getInstance(mode="sql"):
        dm = DocumentManager(mode=mode)
        DMSStorage.fromCache(dm)
        return dm


class FolderManager(EntityManager):
    """
    manager for Archives
    """

    def __init__(self, mode="sql", debug=False):
        """constructor"""
        name = "folder"
        entityName = "Folder"
        entityPluralName = "folders"
        listName = entityPluralName
        clazz = Folder
        tableName = name
        config = DMSStorage.getStorageConfig(mode=mode, debug=debug)
        handleInvalidListTypes = True
        filterInvalidListTypes = True
        primaryKey = None
        super().__init__(
            name,
            entityName,
            entityPluralName,
            listName,
            clazz,
            tableName,
            primaryKey,
            config,
            handleInvalidListTypes,
            filterInvalidListTypes,
            debug,
        )

    @staticmethod
    def getInstance(mode="sql"):
        fm = FolderManager(mode=mode)
        DMSStorage.fromCache(fm)
        return fm

    def getDocumentRecords(self, archiveName, folderPath):
        """
        get the document records
        """
        sqlDB = SQLDB(self.getCacheFile())
        sqlQuery = "SELECT * FROM document WHERE archiveName=(?) AND folderPath=(?)"
        params = (
            archiveName,
            folderPath,
        )
        dictList = sqlDB.query(sqlQuery, params)
        return dictList

    def getFolder(self, archive, folderPath: str):
        """
        get the folder for the given archive and folderPath

        Args:
            archive: the  archive
            folderPath: the path of the folder
        """
        sqlDB = SQLDB(self.getCacheFile())
        sqlQuery = "SELECT * FROM folder WHERE archiveName=(?) AND path=(?)"
        archiveName = archive.name
        params = (
            archiveName,
            folderPath,
        )
        records = sqlDB.query(sqlQuery, params)
        folder = None
        if len(records) > 1:
            msg = f"{len(records)} folders found for {archiveName}:{folderPath} - there should be only one"
            raise Exception(msg)
        elif len(records) == 1:
            folder = Folder()
            folder.fromDict(records[0])
        folder.archive = archive
        return folder

    def refreshFolder(self, archive, folderPath):
        """
        for the given archive and folderPath

        Args:
            archive: the name of the archive
            folderPath: the path of the folder
        """
        folder = self.getFolder(archive, folderPath)
        folder.refreshDocuments()
        pass


@lod_storable
class Archive:
    """
    An Archive might be a filesystem on a server or a (semantic) MediaWiki.
    Maps to the SQLite table 'archive'.

    CREATE TABLE archive (
      name TEXT,
      server TEXT,
      url TEXT PRIMARY KEY,
      wikiid TEXT
    )
    """

    # Core Identification
    name: str = ""  # e.g. "wiki", "bitplan-scan"
    server: str = ""  # e.g. "wiki.bitplan.com", "capri.bitplan.com"
    url: str = ""  # e.g. "http://wiki.bitplan.com" (PRIMARY KEY)
    wikiid: Optional[str] = None  # e.g. "wiki", or NULL for non-wiki archives

    # Calculated/Aggregate Metrics (based on getSamples, not in CREATE TABLE)
    folderCount: int = 0
    documentCount: int = 0

    # Internal fields for string representation (optional)
    fields: list = field(
        default_factory=lambda: [
            "name",
            "server",
            "url",
            "folderCount",
            "documentCount",
        ],
        init=False,
    )

    def __post_init__(self):
        """
        post Constructor logic
        """

    @classmethod
    def getSamples(cls):
        samplesLOD = [
            {
                "server": "wiki.bitplan.com",
                "name": "wiki",
                "url": "http://wiki.bitplan.com",
                "wikiid": "wiki",
                "folderCount": 0,
                "documentCount": 0,
            },
            {
                "server": "media.bitplan.com",
                "name": "media",
                "url": "http://media.bitplan.com",
                "wikiid": "media",
                "folderCount": 9,
                "documentCount": 551,
            },
        ]
        return samplesLOD

    def normalizePageTitle(self, pageTitle):
        """
        normalize the given pageTitle
        """
        nPageTitle = pageTitle.replace(" ", "_")
        return nPageTitle

    def getFoldersAndDocuments(self, withOcr=False, progress_bar=None):
        """
        get the folders and documents of this archive

        Args:
            withOcr(bool): whether to include OCR text
            progress_bar(Progressbar): a progress bar to track progress

        Returns:
            dict: foldersByPath and documentList
        """
        foldersByPath = {}
        documentList = []
        # this archive is pointing to a wiki
        if hasattr(self, "wikiid") and self.wikiid is not None:
            smw = Wiki.getSMW(self.wikiid)
            for option in ["|format=count", ""]:
                askQuery = (
                    """{{#ask: [[Category:OCRDocument]]
| mainlabel=page
| ?Category
| ?Modification date=lastModified
| ?Creation date=created
|limit=1000
%s
}}"""
                    % option
                )
                print(askQuery)
                result = smw.query(askQuery)
                baseUrl = f"{smw.site.scheme}://{smw.site.host}{smw.site.path}index.php"
                if option == "":
                    folderCounter = Counter()
                    folderCreated = {}
                    folderLastModified = {}
                    for record in result.values():
                        page = record["page"]
                        if "Kategorie" in record:
                            catname = "Kategorie"
                            categories = record["Kategorie"]
                        else:
                            catname = "Category"
                            categories = record["Category"]
                        doc = Document()
                        doc.archiveName = self.name
                        if isinstance(categories, list):
                            firstCategory = categories[0]
                        else:
                            firstCategory = categories
                        doc.folderPath = firstCategory.replace(f"{catname}:", "")
                        # print(f"{firstCategory}->{doc.folderPath}")
                        doc.lastModified = record["lastModified"]
                        doc.created = record["created"]
                        folderCounter[doc.folderPath] += 1
                        if doc.created:
                            if doc.folderPath in folderCreated:
                                folderCreated[doc.folderPath] = min(
                                    doc.created, folderCreated[doc.folderPath]
                                )
                            else:
                                folderCreated[doc.folderPath] = doc.created
                        if doc.lastModified:
                            if doc.folderPath in folderLastModified:
                                folderLastModified[doc.folderPath] = max(
                                    doc.lastModified, folderLastModified[doc.folderPath]
                                )
                            else:
                                folderLastModified[doc.folderPath] = doc.lastModified

                        doc.name = page
                        doc.url = f"{baseUrl}/{self.normalizePageTitle(page)}"
                        documentList.append(doc)
                        if progress_bar:
                            progress_bar.total += 1
                            progress_bar.update_value(progress_bar.value + 1)

                    # collect folders
                    for folderName, count in folderCounter.most_common():
                        folder = Folder()
                        folder.archiveName = self.name
                        folder.name = folderName
                        folder.path = folderName
                        if folderName in folderLastModified:
                            folder.lastModified = folderLastModified[folderName]
                        if folderName in folderCreated:
                            folder.created = folderCreated[folderName]
                        folder.url = f"{baseUrl}/Category:{folderName}"
                        folder.fileCount = count
                        foldersByPath[folderName] = folder
                        if progress_bar:
                            progress_bar.total += 1
                            progress_bar.update_value(progress_bar.value + 1)
                        pass
        else:
            # this archive is pointing to a folder
            pattern = rf"http://{self.server}"
            folderPath = re.sub(pattern, "", self.url)
            basePath = Folder.getFullpath(folderPath)
            for root, dirs, files in os.walk(basePath):
                relbase = Folder.getRelpath(root)
                # loop over all directories
                for dirname in dirs:
                    if not dirname.startswith("."):
                        folder = Folder()
                        folder.archive = self
                        fullpath = os.path.join(root, dirname)
                        folder.path = os.path.join(relbase, dirname)
                        folder.archiveName = self.name
                        folder.url = f"http://{self.server}{folder.path}"
                        folder.name = dirname
                        # files in folder ...
                        pdfFiles = folder.getFiles()
                        folder.fileCount = len(pdfFiles)
                        folder.lastModified = DMSStorage.getDatetime(fullpath)
                        folder.created = folder.lastModified
                        folderDocuments = folder.getDocuments(
                            pdfFiles, withOcr=withOcr, progress_bar=progress_bar
                        )
                        # add the results
                        documentList.extend(folderDocuments)
                        foldersByPath[folder.path] = folder
                        if progress_bar:
                            progress_bar.total += 1
                            progress_bar.update_value(progress_bar.value + 1)

            pass
        return foldersByPath, documentList


class ArchiveManager(EntityManager):
    """
    manager for Archives
    """

    def __init__(self, mode="sql", debug=False):
        """constructor"""
        name = "archive"
        entityName = "Archive"
        entityPluralName = "archives"
        listName = entityPluralName
        clazz = Archive
        tableName = name
        config = DMSStorage.getStorageConfig(mode=mode, debug=debug)
        handleInvalidListTypes = True
        filterInvalidListTypes = True
        primaryKey = "url"
        super().__init__(
            name,
            entityName,
            entityPluralName,
            listName,
            clazz,
            tableName,
            primaryKey,
            config,
            handleInvalidListTypes,
            filterInvalidListTypes,
            debug,
        )

    @staticmethod
    def getInstance(mode=None):
        if mode is None:
            ams = ArchiveManager(mode="sql")
            if not ams.isCached():
                amj = ArchiveManager(mode="json")
                amj.fromCache()
                ams.archives = amj.archives
                ams.store()
            am = ams
            DMSStorage.fromCache(ams)
            am = ams
        else:
            am = ArchiveManager(mode)
        am.archives_by_name, am.duplicate_archives = am.getLookup("name")

        if am.duplicate_archives:
            duplicate_names = [a.name for a in am.duplicate_archives[:5]]
            names_str = ", ".join(duplicate_names)
            warn_msg = f"Found {len(am.duplicate_archives)} archives with duplicate names. First 5 duplicates: {names_str}"
            if len(am.duplicate_archives) > 5:
                warn_msg += " ..."
            logging.warning(warn_msg)
        return am

    @staticmethod
    def addFilesAndFoldersForArchive(
        archive=None, withOcr=False, progress_bar=None, store=False, debug=True
    ):
        """
        add Files and folder for the given Archive

        Args:
            archive(Archive): the archive to add files and folder for
            store(bool): True if the result should be stored in the storage
            progress_bar(Progressbar): A Progressbar instance for tracking progress
            debug(bool): True if debugging messages should be displayed
        """
        if archive is None:
            return
        folders = []
        msg = f"getting folders for {archive.name}"
        if debug:
            print(msg)
        afoldersByPath, documentList = archive.getFoldersAndDocuments(
            withOcr=withOcr, progress_bar=progress_bar
        )
        folderCount = len(afoldersByPath)
        msg = f"found {folderCount} folders in {archive.name}"
        folders.extend(afoldersByPath.values())
        if debug:
            print(msg)
        if store:
            if len(folders) > 0:
                fms = FolderManager(mode="sql")
                fms.folders = folders
                fms.store(append=True, replace=True)
            if len(documentList) > 0:
                dms = DocumentManager(mode="sql")
                dms.documents = documentList
                dms.store(append=True, replace=True)
