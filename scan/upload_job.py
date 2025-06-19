"""
Created on 2025-04-07

@author: wf

"""

from basemkit.yamlable import lod_storable


@lod_storable
class UploadJob:
    """
    Job description for document upload
    """

    file_path: str  # the pdf or jpg file to upload
    page_title: str = None
    categories: str = None
    topic: str = None
    wiki_id: str = None
    ocr_text: str = None
    description: str = None
