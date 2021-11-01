'''
Created on 2021-10-21

@author: wf

see http://diagrams.bitplan.com/render/png/0xe1f1d160.png
see http://diagrams.bitplan.com/render/txt/0xe1f1d160.txt

'''
from lodstorage.storageconfig import StorageConfig, StoreMode
from lodstorage.jsonable import JSONAble
from lodstorage.sql import SQLDB
from lodstorage.entity import EntityManager 
from datetime import datetime
from collections import Counter
import re
import os
import sys
from wikibot.wikiclient import WikiClient
from wikibot.smw import SMWClient
class Wiki(object):
    
    @staticmethod
    def getSMW(wikiId):
        wikiClient=Wiki.get(wikiId)
        smw=SMWClient(wikiClient.getSite())
        return smw    
    
    @staticmethod
    def get(wikiId):
        wikiClient=WikiClient.ofWikiId(wikiId)
        wikiClient.login()
        return wikiClient

class DMSStorage:
    '''
    Document management system storage configuration
    '''
    profile=True
    withShowProgress=True
    
    @staticmethod
    def getStorageConfig(debug:bool=False,mode='sql')->StorageConfig:
        '''
        get the storageConfiguration
        
        Args:
            debug(bool): if True show debug information
            mode(str): sql or json
        
        Return:
            StorageConfig: the storage configuration to be used
        '''
        if mode=='sql':
            config=StorageConfig.getSQL(debug=debug)
        elif mode=='json':
            config=StorageConfig.getJSON()
        elif mode=='jsonpickle':
            config=StorageConfig.getJsonPickle(debug=debug)
        else:
            raise Exception(f"invalid mode {mode}")
        config.cacheDirName="dms"
        cachedir=config.getCachePath() 
        config.profile=DMSStorage.profile
        config.withShowProgress=DMSStorage.withShowProgress
        if mode=='sql':
            config.cacheFile=f"{cachedir}/dms.db"
        return config
    
    @staticmethod
    def getSqlDB():
        '''
        get the SQlite database connection
        '''
        config=DMSStorage.getStorageConfig(mode="sql")
        # https://stackoverflow.com/a/48234567/1497139
        sqlDB=SQLDB(config.cacheFile,check_same_thread=False)
        return sqlDB
    
    @staticmethod
    def getDatetime(fullpath:str):
        '''
        get the last modification time
        
        Args:
            fullpath(str): the path to get the datetime for
        '''
        timestamp=os.path.getmtime(fullpath)
        ftime=datetime.fromtimestamp(timestamp)
        return ftime
    
    @staticmethod
    def getTimeStr(fullpath:str):
        '''
        get the last modification time
        
        Args:
            fullpath(str): the path to get the time string for
        '''
        ftime=DMSStorage.getDatetime(fullpath)
        ftimestr=ftime.strftime("%Y-%m-%d %H:%M:%S")
        return ftimestr
    
    @staticmethod
    def fromCache(em:EntityManager):
        if em.isCached():
            em.fromCache()
        else:
            if em.config.mode is StoreMode.SQL:
                sqlDB=DMSStorage.getSqlDB()
                em.initSQLDB(sqlDB)
    
class Document(JSONAble):
    '''
    a document consist of one or more files in the filesystem
    or a wikipage - the name is the pagetitle 
    or the filename without extension
    
    types then has the list of available file types e.g. "pdf,txt"
    for single page Documents  the document is somewhat redundant to the Page concept
    '''

    def __init__(self):
        '''
        Constructor
        '''
        
    @classmethod
    def getSamples(cls):
        samplesLOD = [{
    "archiveName": "bitplan-scan",
    "folderPath": "",
    "url":"http://capri.bitplan.com/bitplan/scan/2019/",
    "created": datetime(2019, 2, 27, 10, 7, 56),
    "size": 15,
    "lastModified": datetime(2019, 2, 27, 10, 7, 56),
    "name": "2019",
    "types": "pdf"
}]
        return samplesLOD
    
class Folder(JSONAble):
    '''
    a Folder might be a filesystem folder or a category in a wiki
    '''

    def __init__(self):
        '''
        Constructor
        '''
        
    @classmethod
    def getSamples(cls):
        samplesLOD = [{
    "archiveName": "bitplan-scan",
    "url":"http://capri.bitplan.com/bitplan/scan/2019/",
    "fileCount": 15,
    "lastModified": datetime(2019, 2, 27, 10, 7, 56),
    "created": datetime(2019, 2, 27, 10, 7, 56),
    "name": "2019",
    "path": "/bitplan/scan/2019"
}]
        return samplesLOD
    
    @classmethod
    def getPrefix(cls):
        '''
        get the path prefix for this platform (if any)
        
        Return:
            str: the prefix e.g. /Volumes on Darwin
        '''
        if sys.platform == "darwin":
                prefix=f"/Volumes"
        else:
            prefix=""
        return prefix
            
    @classmethod
    def getFullpath(cls,folderPath:str):
        '''
        get the full path as accessible on my platform
        
        Args:
           folderPath(str): the path of the folder
           
        Return:
            str: the full path of the folder
        '''
        fullPath=f"{Folder.getPrefix()}{folderPath}"
        return fullPath
    
    @classmethod
    def getRelpath(cls,folderPath:str)->str:
        '''
        get the relative path as accessible on my platform
        
        Args:
           folderPath(str): the path of the folder
           
        Return:
            str: the relative path of the folder
        '''
        prefix=Folder.getPrefix()
        if prefix and folderPath.startswith(prefix):
            relbase=folderPath.replace(prefix,"")
        else:
            relbase=folderPath
        return relbase
    
    def logException(self,ex):
        msg=f"{ex}"
        print(msg,file=sys.stderr,flush=True)
        
        
    def getFiles(self,extension=".pdf"):
        '''
        get all files with the given extension
        
        Args:
            extension(str): the extension to search for
            
        Return:
            list: the files with the given extension
        '''
        files=[]
        fullPath=Folder.getFullpath(self.path)
        for file in os.listdir(fullPath):
            if file.endswith(".pdf"):
                files.append(file)
        return files
            
    def getFileDocuments(self):
        '''
        get all documents for the OCRDocument files in this folder
        
        Return:
            list: the list of documents
        '''
        files=self.getFiles()
        documents=self.getDocuments(files)
        return documents
    
    def getDocuments(self,files):
        '''
        get the documents for this folder based on the files from my listdir
        '''
        documentList=[]
        for file in files:
            try:
                if file.endswith(".pdf"):
                    doc=Document()
                    doc.archiveName=self.archiveName
                    doc.folderPath=self.path
                    doc.name=file
                    fullpath=f"{self.getFullpath(self.path)}/{file}"
                    doc.url=f"http://{self.archive.server}{self.path}/{file}"
                    doc.types="pdf"
                    doc.size=os.path.getsize(fullpath)
                    doc.lastModified=DMSStorage.getDatetime(fullpath)
                    doc.created=doc.lastModified
                    documentList.append(doc)  
            except Exception as e:
                self.logException(e)      
        return documentList
    
    def refreshDocuments(self):
        '''
        refresh the documents in this folder
        '''
        doclist=self.getFileDocuments()
        for doc in doclist:
            doc.ocrText=doc.getOcrText()
            pass
        pass
    
class DocumentManager(EntityManager):
    '''
    manager for Documents
    '''
    
    def __init__(self,mode='sql',debug=False):
        '''constructor
        '''
        name="document"
        entityName="Document"
        entityPluralName="documents"
        listName=entityPluralName
        clazz=Document
        tableName=name
        config=DMSStorage.getStorageConfig(mode=mode,debug=debug)
        handleInvalidListTypes=True
        filterInvalidListTypes=True
        primaryKey='url'
        super().__init__(name, entityName, entityPluralName, listName, clazz, tableName, primaryKey, config, handleInvalidListTypes, filterInvalidListTypes, debug)
   
    @staticmethod
    def getInstance(mode='sql'):
        dm=DocumentManager(mode=mode)
        DMSStorage.fromCache(dm)
        return dm
    
class FolderManager(EntityManager):
    '''
    manager for Archives
    '''
    
    def __init__(self,mode='sql',debug=False):
        '''constructor
        '''
        name="folder"
        entityName="Folder"
        entityPluralName="folders"
        listName=entityPluralName
        clazz=Folder
        tableName=name
        config=DMSStorage.getStorageConfig(mode=mode,debug=debug)
        handleInvalidListTypes=True
        filterInvalidListTypes=True
        primaryKey='url'
        super().__init__(name, entityName, entityPluralName, listName, clazz, tableName, primaryKey, config, handleInvalidListTypes, filterInvalidListTypes, debug)
   
    @staticmethod
    def getInstance(mode='sql'):
        fm=FolderManager(mode=mode)
        DMSStorage.fromCache(fm)
        return fm
    
    def getDocumentRecords(self,archiveName,folderPath):
        '''
        get the document records
        '''
        sqlDB=SQLDB(self.getCacheFile())
        sqlQuery="SELECT * FROM document WHERE archiveName=(?) AND folderPath=(?)"
        params=(archiveName,folderPath,)
        dictList=sqlDB.query(sqlQuery, params)
        return dictList
    
    def getFolder(self,archive,folderPath:str):
        '''
        get the folder for the given archive and folderPath
        
        Args:
            archive: the  archive
            folderPath: the path of the folder
        '''
        sqlDB=SQLDB(self.getCacheFile())
        sqlQuery="SELECT * FROM folder WHERE archiveName=(?) AND path=(?)"
        archiveName=archive.name
        params=(archiveName,folderPath,)
        records=sqlDB.query(sqlQuery, params)
        folder=None
        if len(records)>1:
            msg=f"{len(records)} folders found for {archiveName}:{folderPath} - there should be only one"
            raise Exception(msg)
        elif len(records)==1:
            folder=Folder()
            folder.fromDict(records[0])
        folder.archive=archive
        return folder
    
    def refreshFolder(self,archive,folderPath):
        '''
        for the given archive and folderPath
        
        Args:
            archive: the name of the archive
            folderPath: the path of the folder 
        '''
        folder=self.getFolder(archive, folderPath)
        folder.refreshDocuments()
        pass
    
class Archive(JSONAble):
    '''
    an Archive might be a filesystem 
    on a server or a (semantic) mediawiki
    '''

    def __init__(self):
        '''
        Constructor
        '''
        
    @classmethod
    def getSamples(cls):
        samplesLOD = [{
            "server": "wiki.bitplan.com",
            "name": "wiki",
            "url": "http://wiki.bitplan.com",
            "wikiid": "wiki",
            "folderCount": 0,
            "documentCount": 0,
        },{
            "server": "media.bitplan.com",
            "name": "media",
            "url": "http://media.bitplan.com",
            "wikiid": "media",
            "folderCount": 9,
            "documentCount": 551
        }]
        return samplesLOD
    
    def normalizePageTitle(self,pageTitle):
        '''
        normalize the given pageTitle
        '''
        nPageTitle=pageTitle.replace(" ","_")
        return nPageTitle
    
    def getFoldersAndDocuments(self):
        '''
        get the folders of this archive
        
        Return:
            the list of folders and files
        '''
        foldersByPath={} 
        documentList=[]
        # this archive is pointing to a wiki
        if hasattr(self,"wikiid") and self.wikiid is not None:
            smw=Wiki.getSMW(self.wikiid)
            for option in ["|format=count",""]:
                askQuery="""{{#ask: [[Category:OCRDocument]]  
| mainlabel=page
| ?Category
| ?Modification date=lastModified
| ?Creation date=created
|limit=1000
%s
}}""" % option
                print(askQuery)
                result=smw.query(askQuery)
                baseUrl=f"{smw.site.scheme}://{smw.site.host}{smw.site.path}index.php"
                if option=="":
                    folderCounter=Counter()
                    folderCreated={}
                    folderLastModified={}
                    for record in result.values():
                        page=record['page']
                        if "Kategorie" in record:
                            catname="Kategorie"
                            categories=record['Kategorie']
                        else:
                            catname="Category"
                            categories=record['Category']
                        doc=Document()
                        doc.archiveName=self.name
                        if isinstance(categories,list):
                            firstCategory=categories[0]
                        else:
                            firstCategory=categories
                        doc.folderPath=firstCategory.replace(f"{catname}:","")
                        #print(f"{firstCategory}->{doc.folderPath}")
                        doc.lastModified=record["lastModified"]
                        doc.created=record["created"]
                        folderCounter[doc.folderPath]+=1
                        if doc.created:
                            if doc.folderPath in folderCreated:  
                                folderCreated[doc.folderPath]=min(doc.created,folderCreated[doc.folderPath])
                            else:
                                folderCreated[doc.folderPath]=doc.created
                        if doc.lastModified:
                            if doc.folderPath in folderLastModified:
                                folderLastModified[doc.folderPath]=max(doc.lastModified,folderCreated[doc.folderPath])
                            else:
                                folderLastModified[doc.folderPath]=doc.lastModified
                            
                        doc.name=page
                        doc.url=f"{baseUrl}/{self.normalizePageTitle(page)}"
                        documentList.append(doc)
                    # collect folders    
                    for folderName,count in folderCounter.most_common():
                        folder=Folder()
                        folder.archiveName=self.name
                        folder.name=folderName
                        folder.path=folderName
                        folder.lastModified=folderLastModified[folderName]
                        folder.created=folderCreated[folderName]
                        folder.url=f"{baseUrl}/Category:{folderName}"
                        folder.fileCount=count
                        foldersByPath[folderName]=folder
                        pass
        else:
            # this archive is pointing to a folder
            pattern=fr"http://{self.server}"
            folderPath=re.sub(pattern,"",self.url)
            basePath=Folder.getFullpath(folderPath)
            for root, dirs, files in os.walk(basePath):
                relbase=Folder.getRelpath(root)
                # loop over all directories
                for dirname in dirs: 
                    if not dirname.startswith("."):
                        folder=Folder()
                        folder.archive=self
                        fullpath=os.path.join(root,dirname)
                        folder.path=os.path.join(relbase, dirname)
                        folder.archiveName=self.name
                        folder.url=f"http://{self.server}{folder.path}"
                        folder.name=dirname
                        # files in folder ...
                        pdfFiles=folder.getFiles()
                        folder.fileCount=len(pdfFiles)
                        folder.lastModified=DMSStorage.getDatetime(fullpath)
                        folder.created=folder.lastModified
                        folderDocuments=folder.getDocuments(pdfFiles)
                        # add the results
                        documentList.extend(folderDocuments)
                        foldersByPath[folder.path]=folder
            pass
        return foldersByPath,documentList
    
        
class ArchiveManager(EntityManager):
    '''
    manager for Archives
    '''
    
    def __init__(self,mode='sql',debug=False):
        '''constructor
        '''
        name="archive"
        entityName="Archive"
        entityPluralName="archives"
        listName=entityPluralName
        clazz=Archive
        tableName=name
        config=DMSStorage.getStorageConfig(mode=mode,debug=debug)
        handleInvalidListTypes=True
        filterInvalidListTypes=True
        primaryKey='url'
        super().__init__(name, entityName, entityPluralName, listName, clazz, tableName, primaryKey, config, handleInvalidListTypes, filterInvalidListTypes, debug)
   
    @staticmethod
    def getInstance(mode=None):
        if mode is None:
            ams=ArchiveManager(mode='sql')
            if not ams.isCached():
                amj=ArchiveManager(mode='json')
                amj.fromCache()
                ams.archives=amj.archives
                ams.store()
            am=ams
            DMSStorage.fromCache(ams)
            am=ams
        else:
            am=ArchiveManager(mode)
        return am
    
    @staticmethod
    def addFilesAndFoldersForArchive(archive=None,store=False,debug=True):
        '''
        add Files and folder for the given Archive
        
        Args:
            archive(Archive): the archive to add files and folder for
            store(bool): True if the result should be stored in the storage
            debug(bool): True if debugging messages should be displayed
        '''
        if archive is None:
            return
        folders=[]
        msg=f"getting folders for {archive.name}"
        if debug:
            print(msg)
        afoldersByPath,documentList=(archive.getFoldersAndDocuments())
        folderCount=len(afoldersByPath)
        msg=f"found {folderCount} folders in {archive.name}"
        folders.extend(afoldersByPath.values())
        if debug:
                print(msg)
        if store:
            if len(folders)>0:
                fms=FolderManager(mode='sql')
                fms.folders=folders
                fms.store(append=True)
            if len(documentList)>0:
                dms=DocumentManager(mode='sql')
                dms.documents=documentList
                dms.store(append=True)


