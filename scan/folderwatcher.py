'''
Created on 2021-04-21

see https://stackoverflow.com/a/66110795/1497139

'''

import time
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
import sys


class Watcher:
    '''
    watch the given path with the given callback
    '''
    def __init__(self, path,patterns=["*.pdf","*.jpg"],debug=False):
        '''
        construct me for the given path
        Args:
            path(str): the directory to observer
            patterns(list): a list of wildcard patterns
            debug(bool): True if debugging should be switched on
        '''
        self.observer = Observer()
        self.path = path
        self.patterns=patterns
        self.debug=debug

    def run(self,callback,sleepTime=1,limit=sys.maxsize):
        '''
        run me
        
        Args:
            callback(func): the function to trigger when a file appears
            sleepTime(float): how often to check for incoming files - default: 1.0 secs
            limit(float): the maximum time to run the server default: unlimited
        '''
        event_handler = Handler(callback,patterns=self.patterns,debug=self.debug)
        self.observer.schedule(event_handler, self.path, recursive=True)
        self.observer.start()
        runTime=0
        try:
            while runTime<limit:
                time.sleep(sleepTime)
                runTime+=sleepTime
                
        except Exception as ex:
            self.observer.stop()
            if self.debug:
                print("Error %s " % str(ex))

        # don't
        # we won't terminate if we do
        # self.observer.join()


class Handler(PatternMatchingEventHandler):
    '''
    handle changes for a given wildcard pattern
    '''
    def __init__(self,callback,patterns,debug=False):
        '''
        construct me
        
        Args:
            callback: the function to call
            patterns: the patterns to trigger on
            debug(bool): if True print debug output
        '''
        self.callback=callback
        self.debug=debug
        # Set the patterns for PatternMatchingEventHandler
        PatternMatchingEventHandler.__init__(
            self,
            patterns=patterns,
            ignore_directories=True,
            case_sensitive=False,
        )

    def on_any_event(self, event):
        if self.debug:
            print(
                "[{}] noticed: [{}] on: [{}] ".format(
                    time.asctime(), event.event_type, event.src_path
                )
                
            )
        if "modified" == event.event_type:
            self.callback(event.src_path)
            
        
