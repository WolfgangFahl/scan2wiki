'''
Created on 2021-10-21

@author: wf

see http://diagrams.bitplan.com/render/png/0xe1f1d160.png
see http://diagrams.bitplan.com/render/txt/0xe1f1d160.txt

'''

class Archive(object):
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
            "server": "media.bitplan.com",
            "name": "media",
            "url": "http://media.bitplan.com",
            "wikiid": "media",
        }]
        return samplesLOD
        