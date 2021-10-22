'''
Created on 2021-10-21

@author: wf

see http://diagrams.bitplan.com/render/png/0xe1f1d160.png
see http://diagrams.bitplan.com/render/txt/0xe1f1d160.txt

'''
from lodstorage.jsonable import JSONAble
from lodstorage.entity import EntityManager
from lodstorage.storageconfig import StorageConfig
from datetime import datetime
import re
import os
import sys

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
    def getTimeStr(fullpath:str):
        '''
        get the last modification time
        
        Args:
            fullpath(str): the path to get the time string for
        '''
        timestamp=os.path.getmtime(fullpath)
        ftime=datetime.fromtimestamp(timestamp)
        ftimestr=ftime.strftime("%Y-%m-%d %H:%M:%S")
        return ftimestr
    
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
    "created": "2021-10-22 17:06:16",
    "size": 15,
    "lastModified": "2021-10-22 17:06:16",
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
    "lastModified": "2021-10-22 17:06:16",
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
                    doc.lastModified=DMSStorage.getTimeStr(fullpath)
                    documentList.append(doc)  
            except Exception as e:
                print(str(e))      
        return documentList
    
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
        dm.fromCache()
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
        fm.fromCache()
        return fm
    
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
        },{
            "server": "media.bitplan.com",
            "name": "media",
            "url": "http://media.bitplan.com",
            "wikiid": "media",
        }]
        return samplesLOD
    
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
            askQuery=""
        else:
            # this archive is pointing to folder
            pattern=fr"http://{self.server}"
            folderPath=re.sub(pattern,"",self.url)
            basePath=Folder.getFullpath(folderPath)
            for root, dirs, files in os.walk(basePath):
                relbase=Folder.getRelpath(root)
                for dirname in dirs: 
                    if not dirname.startswith("."):
                        folder=Folder()
                        folder.archive=self
                        fullpath=os.path.join(root,dirname)
                        folder.path=os.path.join(relbase, dirname)
                        folder.archiveName=self.name
                        folder.url=f"http://{self.server}{folder.path}"
                        folder.name=dirname
                        folder.fileCount=len(os.listdir(fullpath))
                        folder.lastModified=DMSStorage.getTimeStr(fullpath)
                        foldersByPath[folder.path]=folder 
                if relbase in foldersByPath:
                    folder=foldersByPath[relbase]
                    folderDocuments=folder.getDocuments(files)
                    documentList.extend(folderDocuments)
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
    def getInstance(mode='json'):
        am=ArchiveManager(mode=mode)
        am.fromCache()
        return am
    
    


