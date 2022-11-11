'''
Created on 2021-10-22

@author: wf
'''
from unittest import TestCase
import getpass
import warnings
from scan.profiler import Profiler
import logging


class BaseTest(TestCase):
    '''
    base Test class
    '''
    
    def setUp(self,debug=False,profile=True):
        '''
        setUp test environment
        '''
        TestCase.setUp(self)
        self.debug=debug
        msg=(f"test {self._testMethodName} ... with debug={self.debug}")
        self.profiler=Profiler(msg=msg,profile=profile)
        self.profiler.start()
        warnings.simplefilter("ignore", ResourceWarning)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        
    def tearDown(self):
        _elapsed,_elapsedMessage=self.profiler.time()
        pass
        
    @staticmethod    
    def isInPublicCI():
        '''
        are we running in a public Continuous Integration Environment?
        '''
        return getpass.getuser() in [ "travis", "runner" ];
    
    def inPublicCI(self):
        return BaseTest.isInPublicCI()
        
