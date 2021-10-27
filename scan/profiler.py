'''
Created on 2021-10-26

@author: wf
'''
import time

class Profiler:
    '''
    simple profiler
    '''
    def __init__(self,msg,profile=True):
        '''
        construct me with the given msg and profile active flag
        
        Args:
            msg(str): the message to show if profiling is active
            profile(bool): True if messages should be shown
        '''
        self.msg=msg
        self.profile=profile
        
        
    def start(self)->str:
        '''
        start profiling
        
        Return:
            str: start message
        '''
        msg=f"Starting {self.msg} ..."
        self.starttime=time.time()
        if self.profile:
            print(msg)
        return msg
        
    
    def time(self,extraMsg=""):
        '''
        time the action and print if profile is active
        
        Return:
            (float,str): time and message for time
        '''
        elapsed=time.time()-self.starttime
        elapsedMessage=f"{self.msg}{extraMsg} took {elapsed:5.3f} s"
        if self.profile:
            print(elapsedMessage)
        return elapsed,elapsedMessage