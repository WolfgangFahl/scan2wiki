'''
Created on 2021-11-02

@author: wf
'''
#import sys
import logging

class Logger(object):
    '''
    a logger module
    '''
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    @staticmethod
    def log(msg:str):
        Logger.logger.info(msg)

    @staticmethod
    def logException(ex):
        #msg=f"{ex}"
        #print(msg,file=sys.stderr,flush=True)
        Logger.logger.exception(ex)