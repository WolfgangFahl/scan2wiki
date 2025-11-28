"""
Created on 2020-08-19

@author: wf
"""

import datetime
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Type

from lodstorage.lod import LOD
from lodstorage.sparql import SPARQL
from lodstorage.sql import SQLDB
from lodstorage.storageconfig import StorageConfig, StoreMode

class JsonCache():
    """
    JSON cache mixin
    """
    def store_to_json_file(
        self,
        cacheFile: str,
        listOfDicts: List[Dict[str, Any]] = None,
        pretty: bool = True
    ):
        """
        Store the current list of entities to a JSON file.

        Args:
            cacheFile (str): The path to the file where JSON data should be stored.
            listOfDicts (List[Dict[str, Any]]): Optional list of dicts to store;
                                                 if None, uses self.getLoD().
            pretty (bool): If True, format the JSON with indentation.
        """

        # Ensure the directory exists
        dir_path = os.path.dirname(cacheFile)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Serialize using internal to_json to handle dates and custom types correctly.
        # We set limit_to_sample_fields=False because a cache store should typically
        # preserve all available data, not just fields defined in samples.
        json_str = self.to_json(lod=listOfDicts,pretty=pretty, limit_to_sample_fields=False)

        with open(cacheFile, "w", encoding="utf-8") as f:
            f.write(json_str)

    def read_lod_from_json_file(self, cacheFile: str) -> List[Dict[str, Any]]:
        """
        Read a list of dictionaries from a JSON file.

        Args:
            cacheFile (str): The path to the JSON file.

        Returns:
            list: A list of dictionaries loaded from the JSON file.
        """
        if not os.path.isfile(cacheFile):
            return []

        with open(cacheFile, "r", encoding="utf-8") as f:
            lod = json.load(f)

        return lod

    def to_json(
        self,
        pretty: bool = False,
        sort_keys: bool = False,
        limit_to_sample_fields: bool = True,
        lod: List[Dict[str, Any]] = None,
    ) -> str:
        """
        Serialize the current entities to a JSON string.

        Args:
            pretty (bool): If True, pretty-print with indentation.
            sort_keys (bool): If True, sort keys in output.
            limit_to_sample_fields (bool): If True, only serialize fields declared
                                           in the class `getSamples` method.
            lod (list): Optional list of dicts to serialize; if None, uses self.getLoD().

        Returns:
            str: JSON string representing the list of entities.
        """
        if lod is None:
            lod = self.getLoD()

        # Filter fields based on getSamples logic
        if limit_to_sample_fields and self.clazz is not None:
            samples = self.get_samples_for_class(self.clazz)
            if samples:
                # Collect all unique keys defined in all sample records
                # This handles cases where samples might have optional fields
                valid_keys = set().union(*(sample.keys() for sample in samples))

                # Filter the lod to only contain keys present in the samples
                lod = [
                    {key: record.get(key) for key in valid_keys if key in record}
                    for record in lod
                ]

        def _default(obj):
            # Handle common non-JSON-native types gracefully
            if isinstance(obj, (datetime.datetime, datetime.date)):
                return obj.isoformat()
            if isinstance(obj, set):
                return list(obj)
            # Respect custom conversion hooks if present
            if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
                return obj.to_dict()
            if hasattr(obj, "to_json") and callable(getattr(obj, "to_json")):
                # In case nested entities implement to_json returning a string,
                # we unpack it to avoid double serialization strings
                try:
                    return json.loads(obj.to_json())
                except Exception:
                    pass
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            # Fallback to string
            return str(obj)

        json_str = json.dumps(
            lod,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=sort_keys,
            default=_default,
        )
        return json_str

class EntityManager(JsonCache):
    """
    generic entity manager
    """

    def __init__(
        self,
        name,
        entityName,
        entityPluralName: str,
        listName: str = None,
        clazz=None,
        tableName: str = None,
        primaryKey: str = None,
        config=None,
        handleInvalidListTypes=False,
        filterInvalidListTypes=False,
        listSeparator="⇹",
        debug=False,
    ):
        """
        Constructor

        Args:
            name(string): name of this eventManager
            entityName(string): entityType to be managed e.g. Country
            entityPluralName(string): plural of the the entityType e.g. Countries
            config(StorageConfig): the configuration to be used if None a default configuration will be used
            handleInvalidListTypes(bool): True if invalidListTypes should be converted or filtered
            filterInvalidListTypes(bool): True if invalidListTypes should be deleted
            listSeparator(str): the symbol to use as a list separator
            debug(boolean): override debug setting when default of config is used via config=None
        """
        self.logger = logging.getLogger(__name__)
        self.name = name
        self.entityName = entityName
        self.entityPluralName = entityPluralName
        if listName is None:
            listName = entityPluralName
        if tableName is None:
            tableName = entityName
        self.primaryKey = primaryKey
        if config is None:
            config = StorageConfig.getDefault()
        if debug:
            config.debug = debug
        self.config = config
        #super(EntityManager, self).__init__(
        #    listName=listName,
        #    clazz=clazz,
        #    tableName=tableName,
        #    handleInvalidListTypes=handleInvalidListTypes,
        #    filterInvalidListTypes=filterInvalidListTypes,
        #)
        self.list=[]
        self.lod=[]
        self.listName = listName
        # This ensures self.<listName> (e.g., self.archives) points to self.list
        setattr(self, self.listName, self.list)

        self.clazz = clazz
        self.tableName = tableName
        self.handleInvalidListTypes = handleInvalidListTypes
        self.filterInvalidListTypes = filterInvalidListTypes

        cacheFile = self.getCacheFile(config=config, mode=config.mode)
        self.showProgress(
            f"Creating {self.entityName}manager({config.mode}) for {self.name} using cache {cacheFile}"
        )
        if config.mode is StoreMode.SPARQL:
            if config.endpoint is None:
                raise Exception("no endpoint set for mode sparql")
            self.endpoint = config.endpoint
            self.sparql = SPARQL(
                config.endpoint, debug=config.debug, profile=config.profile
            )
        elif config.mode is StoreMode.SQL:
            self.executeMany = False  # may be True when issues are fixed
        self.listSeparator = listSeparator

    def storeMode(self):
        """
        return my store mode
        """
        return self.config.mode

    def get_samples_for_class(self, cls: Type[Any]) -> List[Dict[str, Any]]:
        """
        Retrieves sample data (List of Dictionaries) for a given class.

        This function expects the class to implement a static/class method
        named 'getSamples'.

        Args:
            cls: The class object (e.g., Document, Folder, Archive).

        Returns:
            A list of dictionaries containing sample data for the class.
        """
        lod=[]
        if hasattr(cls, 'getSamples') and callable(getattr(cls, 'getSamples')):
            # Call the getSamples class method
            lod=cls.getSamples()
        else:
            # Handle cases where the class does not have the required method
            # Handle cases where the class does not have the required method
            self.logger.warning("Class %s does not implement getSamples().", cls.__name__)
        return lod

    def showProgress(self, msg):
        """display a progress message

        Args:
          msg(string): the message to display
        """
        if self.config.withShowProgress:
            print(msg, flush=True)

    def getCacheFile(self, config=None, mode=StoreMode.SQL):
        """
        get the cache file for this event manager
        Args:
            config(StorageConfig): if None get the cache for my mode
            mode(StoreMode): the storeMode to use
        """
        if config is None:
            config = self.config
        cachedir = config.getCachePath()
        if config.cacheFile is not None:
            return config.cacheFile
        """ get the path to the file for my cached data """
        if mode is StoreMode.JSON or mode is StoreMode.JSONPICKLE:
            extension = f".{mode.name.lower()}"
            cachepath = f"{cachedir}/{self.name}-{self.listName}{extension}"
        elif mode is StoreMode.SPARQL:
            cachepath = f"SPARQL {self.name}:{config.endpoint}"
        elif mode is StoreMode.SQL:
            cachepath = f"{cachedir}/{self.name}.db"
        else:
            cachepath = f"undefined cachepath for StoreMode {mode}"
        return cachepath

    def removeCacheFile(self):
        """remove my cache file"""
        mode = self.config.mode
        if mode is StoreMode.JSON or mode is StoreMode.JSONPICKLE:
            cacheFile = self.getCacheFile(mode=mode)
            if os.path.isfile(cacheFile):
                os.remove(cacheFile)

    def getSQLDB(self, cacheFile):
        """
        get the SQL database for the given cacheFile

        Args:
            cacheFile(string): the file to get the SQL db from
        """
        config = self.config
        sqldb = self.sqldb = SQLDB(
            cacheFile, debug=config.debug, errorDebug=config.errorDebug
        )
        return sqldb

    def initSQLDB(
        self,
        sqldb,
        listOfDicts=None,
        withCreate: bool = True,
        withDrop: bool = True,
        sampleRecordCount=-1,
    ):
        """
        initialize my sql DB

        Args:
            listOfDicts(list): the list of dicts to analyze for type information
            withDrop(boolean): true if the existing Table should be dropped
            withCreate(boolean): true if the create Table command should be executed - false if only the entityInfo should be returned
            sampleRecordCount(int): the number of records to analyze for type information
        Return:
            EntityInfo: the entity information such as CREATE Table command
        """
        # if we get no data we try to get the schema from the samples
        if listOfDicts is None:
            listOfDicts = self.get_samples_for_class(self.clazz)
            if not listOfDicts:
                msg=f"No sample data available for {self.tableName}"
                raise ValueError(msg)

        entityInfo = sqldb.createTable(
            listOfDicts,
            self.tableName,
            primaryKey=self.primaryKey,
            withCreate=withCreate,
            withDrop=withDrop,
            sampleRecordCount=sampleRecordCount,
        )
        return entityInfo

    def setNone(self, record, fields):
        """
        make sure the given fields in the given record are set to none
        Args:
            record(dict): the record to work on
            fields(list): the list of fields to set to None
        """
        LOD.setNone(record, fields)

    def isCached(self):
        """check whether there is a file containing cached
        data for me"""
        result = False
        config = self.config
        mode = self.config.mode
        if mode is StoreMode.JSON or mode is StoreMode.JSONPICKLE:
            result = os.path.isfile(self.getCacheFile(config=self.config, mode=mode))
        elif mode is StoreMode.SPARQL:
            # @FIXME - make abstract
            query = (
                config.prefix
                + """
SELECT  ?source (COUNT(?source) AS ?sourcecount)
WHERE {
   ?event cr:Event_source ?source.
}
GROUP by ?source
"""
            )
            sourceCountList = self.sparql.queryAsListOfDicts(query)
            for sourceCount in sourceCountList:
                source = sourceCount["source"]
                recordCount = sourceCount["sourcecount"]
                if source == self.name and recordCount > 100:
                    result = True
        elif mode is StoreMode.SQL:
            cacheFile = self.getCacheFile(config=self.config, mode=StoreMode.SQL)
            if os.path.isfile(cacheFile):
                sqlQuery = f"SELECT COUNT(*) AS count FROM {self.tableName}"
                try:
                    sqlDB = self.getSQLDB(cacheFile)
                    countResults = sqlDB.query(sqlQuery)
                    countResult = countResults[0]
                    count = countResult["count"]
                    result = count >= 0
                except Exception as ex:
                    msg = str(ex)
                    if self.debug:
                        print(msg, file=sys.stderr)
                        sys.stderr.flush()
                    # e.g. sqlite3.OperationalError: no such table: Event_crossref
                    pass
        else:
            raise Exception(f"unsupported store mode {mode}")
        return result

    def fromCache(
        self,
        force: bool = False,
        getListOfDicts=None,
        append=False,
        sampleRecordCount=-1,
    ):
        """
        get my entries from the cache or from the callback provided

        Args:
            force(bool): force ignoring the cache
            getListOfDicts(callable): a function to call for getting the data
            append(bool): True if records should be appended
            sampleRecordCount(int): the number of records to analyze for type information

        Returns:
            the list of Dicts and as a side effect setting self.cacheFile
        """
        if not self.isCached() or force:
            startTime = time.time()
            self.showProgress(f"getting {self.entityPluralName} for {self.name} ...")
            if getListOfDicts is None:
                if hasattr(self, "getListOfDicts"):
                    getListOfDicts = self.getListOfDicts
                else:
                    raise Exception(
                        "from Cache failed and no secondary cache via getListOfDicts specified"
                    )
            listOfDicts = getListOfDicts()
            duration = time.time() - startTime
            self.showProgress(
                f"got {len(listOfDicts)} {self.entityPluralName} in {duration:5.1f} s"
            )
            self.cacheFile = self.storeLoD(
                listOfDicts, append=append, sampleRecordCount=sampleRecordCount
            )
            self.setListFromLoD(listOfDicts)
        else:
            # fromStore also sets self.cacheFile
            listOfDicts = self.fromStore()
        return listOfDicts

    def fromStore(self, cacheFile=None, setList: bool = True) -> list:
        """
        restore me from the store
        Args:
            cacheFile(String): the cacheFile to use if None use the pre configured cachefile
            setList(bool): if True set my list with the data from the cache file

        Returns:
            list: list of dicts or JSON entitymanager
        """
        startTime = time.time()
        if cacheFile is None:
            cacheFile = self.getCacheFile(config=self.config, mode=self.config.mode)
        self.cacheFile = cacheFile
        self.showProgress(
            "reading %s for %s from cache %s"
            % (self.entityPluralName, self.name, cacheFile)
        )
        mode = self.config.mode
        if mode is StoreMode.JSONPICKLE:
            err_msg=f"""The JSONPICKLE store mode has been deprecated for
You need to switch to a supported mode like StoreMode.SQL or StoreMode.JSON to be able to use fromStore"""
            raise NotImplementedError(err_msg)
        elif mode is StoreMode.JSON:
            listOfDicts = self.read_lod_from_json_file(cacheFile)
            # Fix for wrapped lists e.g. {"archives": [...]}
            if isinstance(listOfDicts, dict) and self.listName in listOfDicts:
                listOfDicts = listOfDicts[self.listName]
            pass
        elif mode is StoreMode.SPARQL:
            # @FIXME make abstract
            eventQuery = (
                """
PREFIX cr: <http://cr.bitplan.com/>
SELECT ?eventId ?acronym ?series ?title ?year ?country ?city ?startDate ?endDate ?url ?source WHERE {
   OPTIONAL { ?event cr:Event_eventId ?eventId. }
   OPTIONAL { ?event cr:Event_acronym ?acronym. }
   OPTIONAL { ?event cr:Event_series ?series. }
   OPTIONAL { ?event cr:Event_title ?title. }
   OPTIONAL { ?event cr:Event_year ?year.  }
   OPTIONAL { ?event cr:Event_country ?country. }
   OPTIONAL { ?event cr:Event_city ?city. }
   OPTIONAL { ?event cr:Event_startDate ?startDate. }
   OPTIONAL { ?event cr:Event_endDate ?endDate. }
   OPTIONAL { ?event cr:Event_url ?url. }
   ?event cr:Event_source ?source FILTER(?source='%s').
}
"""
                % self.name
            )
            listOfDicts = self.sparql.queryAsListOfDicts(eventQuery)
        elif mode is StoreMode.SQL:
            sqlQuery = "SELECT * FROM %s" % self.tableName
            sqlDB = self.getSQLDB(cacheFile)
            listOfDicts = sqlDB.query(sqlQuery)
            sqlDB.close()
            pass
        else:
            raise Exception(f"unsupported store mode {self.config.mode}")

        self.showProgress(
            "read %d %s from %s in %5.1f s"
            % (
                len(listOfDicts),
                self.entityPluralName,
                self.name,
                time.time() - startTime,
            )
        )
        if setList:
            self.setListFromLoD(listOfDicts)
        return listOfDicts

    def setListFromLoD(self, listOfDicts: list):
        """

        Args:
            listOfDicts: The list of dictionaries to load.
        """
        self.list=[]
        for record in listOfDicts:
            entity = self.clazz.from_dict(record)
            self.list.append(entity)
        # Update the alias to point to the new list object
        if self.listName:
            setattr(self, self.listName, self.list)


    def getList(self):
        return self.list



    def getLookup(self, attrName: str, withDuplicates: bool = False) -> tuple:
        """
        Creates a lookup dictionary by the given attribute name, delegating
        the task to the static LOD helper.

        Args:
            attrName: The attribute name to use as the key (e.g., 'name').
            withDuplicates: Whether to return a dictionary of items that had duplicates.

        Returns:
            A tuple: (lookup_dict, duplicates_dict).
        """
        lookup, duplicates = LOD.getLookup(self.getLoD(), attrName, withDuplicates=withDuplicates)

        return lookup, duplicates

    def getLoD(self, limit_to_sample_fields: bool = False) -> List[Dict[str, Any]]:
        """
        Return the LoD of the entities in the list

        Args:
            limit_to_sample_fields(bool): if True filter key by getSamples()

        Return:
            list: a list of Dicts
        """
        lod = []
        valid_keys = None

        # Determine valid keys if filtering is requested
        if limit_to_sample_fields and self.clazz is not None:
            samples = self.get_samples_for_class(self.clazz)
            if samples:
                valid_keys = set().union(*(sample.keys() for sample in samples))

        for entity in self.getList():
            record = entity.__dict__
            if valid_keys:
                # Filter dict to only include keys present in samples
                record = {k: v for k, v in record.items() if k in valid_keys}
            lod.append(record)
        return lod


    def store(
        self,
        limit=10000000,
        batchSize=250,
        append=False,
        fixNone=True,
        sampleRecordCount=-1,
        replace: bool = False,
    ) -> str:
        """
        store my list of dicts

        Args:
            limit(int): maximum number of records to store per batch
            batchSize(int): size of batch for storing
            append(bool): True if records should be appended
            fixNone(bool): if True make sure the dicts are filled with None references for each record
            sampleRecordCount(int): the number of records to analyze for type information
            replace(bool): if True allow replace for insert

        Return:
            str: The cache_file being used
        """
        lod = self.getLoD()
        cache_file= self.storeLoD(
            lod,
            limit=limit,
            batchSize=batchSize,
            append=append,
            fixNone=fixNone,
            sampleRecordCount=sampleRecordCount,
            replace=replace,
        )
        return cache_file

    def storeLoD(
        self,
        listOfDicts,
        limit=10000000,
        batchSize=250,
        cacheFile=None,
        append=False,
        fixNone=True,
        sampleRecordCount=1,
        replace: bool = False,
    ) -> str:
        """
        store my entities

        Args:
            listOfDicts(list): the list of dicts to store
            limit(int): maximum number of records to store
            batchSize(int): size of batch for storing
            cacheFile(string): the name of the storage e.g path to JSON or sqlite3 file
            append(bool): True if records should be appended
            fixNone(bool): if True make sure the dicts are filled with None references for each record
            sampleRecordCount(int): the number of records to analyze for type information
            replace(bool): if True allow replace for insert
        Return:
            str: The cachefile being used
        """
        config = self.config
        mode = config.mode
        if self.handleInvalidListTypes:
            LOD.handleListTypes(
                lod=listOfDicts,
                doFilter=self.filterInvalidListTypes,
                separator=self.listSeparator,
            )
        if mode is StoreMode.JSON or mode is StoreMode.JSONPICKLE:
            if cacheFile is None:
                cacheFile = self.getCacheFile(config=self.config, mode=mode)
            self.showProgress(
                f"storing {len(listOfDicts)} {self.entityPluralName} for {self.name} to cache {cacheFile}"
            )
            if mode is StoreMode.JSONPICKLE:
                raise NotImplementedError(
                    "The JSONPICKLE store mode has been deprecated. Use StoreMode.SQL or StoreMode.JSON."
                )
            if mode is StoreMode.JSON:
                self.store_to_json_file(cacheFile,listOfDicts=listOfDicts)
                pass
        elif mode is StoreMode.SPARQL:
            startTime = time.time()
            msg = f"storing {len(listOfDicts)} {self.entityPluralName} to {self.config.mode} ({self.config.endpoint})"
            self.showProgress(msg)
            # @ FIXME make abstract /configurable
            entityType = "cr:Event"
            prefixes = self.config.prefix
            self.sparql.insertListOfDicts(
                listOfDicts,
                entityType,
                self.primaryKey,
                prefixes,
                limit=limit,
                batchSize=batchSize,
            )
            self.showProgress(
                "store for %s done after %5.1f secs"
                % (self.name, time.time() - startTime)
            )
        elif mode is StoreMode.SQL:
            startTime = time.time()
            if cacheFile is None:
                cacheFile = self.getCacheFile(config=self.config, mode=self.config.mode)
            sqldb = self.getSQLDB(cacheFile)
            self.showProgress(
                "storing %d %s for %s to %s:%s"
                % (
                    len(listOfDicts),
                    self.entityPluralName,
                    self.name,
                    config.mode,
                    cacheFile,
                )
            )
            if append:
                withDrop = False
                withCreate = False
            else:
                withDrop = True
                withCreate = True
            entityInfo = self.initSQLDB(
                sqldb,
                listOfDicts,
                withCreate=withCreate,
                withDrop=withDrop,
                sampleRecordCount=sampleRecordCount,
            )
            self.sqldb.store(
                listOfDicts,
                entityInfo,
                executeMany=self.executeMany,
                fixNone=fixNone,
                replace=replace,
            )
            self.showProgress(
                "store for %s done after %5.1f secs"
                % (self.name, time.time() - startTime)
            )
        else:
            raise Exception(f"unsupported store mode {self.mode}")
        return cacheFile
