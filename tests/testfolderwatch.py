'''
Created on 2021-04-10

@author: wf
'''
import unittest
from scan.folderwatcher import Watcher
import os
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import time

class TestFolderWatch(unittest.TestCase):


    def setUp(self):
        pass


    def tearDown(self):
        pass
    
    def onFileEvent(self):
        pass
    
    def addFile(self,watchdir):
        path="%s/hello.txt" % watchdir
        with open(path, 'w') as file:
            file.write("hello")

    def testFolderWatch(self):
        watchdir="/tmp/folderwatch"
        os.makedirs(watchdir,exist_ok=True)
        watcher=Watcher(watchdir,patterns=["*.txt"])
        sleepTime=1
        limit=3
        scheduler = BackgroundScheduler()
        now=datetime.datetime.now()
        run_date=now+datetime.timedelta(seconds=1)
        scheduler.add_job(self.addFile, 'date',run_date=run_date,kwargs={"watchdir":watchdir})
        scheduler.start()
        watcher.run(self.onFileEvent, sleepTime, limit)
        
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()