"""
Created on 2023-11-16

@author: wf
"""
import logging
from pyzbar.pyzbar import decode
from PIL import Image
from dataclasses import dataclass
from typing import Optional,List

@dataclass
class Barcode:
    """
    Barcode data structure with
    static methods e.g.  e.g. pyzbar barcode decoder wrapper
    """
    code: str
    type: str
    orientation: str
    rect: Optional[dict] = None
    polygon: Optional[List[dict]] = None
    quality: Optional[int] = None
 
   
    @staticmethod
    def decode(image_file_path: str,debug: bool = False):
        """
        Decodes barcodes from the image at the given file path.

        Args:
            image_file_path (str): The file path of the image to decode.
            debug (bool): If False, suppress debug information of the PIL library. Default is False.

        Returns:
            list[Barcode]: A list of Barcode objects, or an empty list if no barcodes are found.
        """
        if not debug:
            # Suppress debug messages
            logging.getLogger("PIL").setLevel(logging.INFO)
        # Open the saved image
        image = Image.open(image_file_path)
        # Decode barcodes
        barcodes = decode(image)
        barcode_list=[Barcode(
            code=barcode.data.decode('utf-8'),
            type=barcode.type,
            rect=barcode.rect._asdict(),
            polygon=[point._asdict() for point in barcode.polygon],
            quality=barcode.quality,
            orientation=barcode.orientation
        ) for barcode in barcodes]
        return barcode_list