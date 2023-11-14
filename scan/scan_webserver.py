"""
Created on 2023-11-14

@author: wf
"""
import os
from ngwidgets.input_webserver import InputWebserver
from ngwidgets.webserver import WebserverConfig
from scan.version import Version

class ScanWebServer(InputWebserver):
    """
    server for Document Management system with option to scan to Semantic Mediawikis
    """
    @classmethod
    def get_config(cls)->WebserverConfig:
        """
        get the configuration for this Webserver
        """
        copy_right="(c)2020-2023 Wolfgang Fahl"
        config=WebserverConfig(copy_right=copy_right,version=Version(),default_port=8334)
        return config
    
    def __init__(self):
        """Constructs all the necessary attributes for the WebServer object."""
        InputWebserver.__init__(self,config=ScanWebServer.get_config())
        
    @classmethod
    def examples_path(cls)->str:
        # the root directory (default: examples)
        path = os.path.join(os.path.dirname(__file__), '../scan2wiki_examples')
        path = os.path.abspath(path)
        return path
  