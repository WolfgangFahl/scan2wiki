"""
Created on 2023-11-16

@author: wf
"""
from ngwidgets.basetest import Basetest
from scan.scan_webserver import ScanWebServer
from scan.barcode import Barcode
import os

class TestBarcode(Basetest):
    """
    test the barcode reading
    """
    
    def test_barcodes(self):
        """
        test decoding sample barcodes
        """
        expected_dict = {
            'passengers_barcode.jpg': Barcode(
                code='4030521749429', 
                type='EAN13', 
                orientation='UP'
            ),
            'webcam_2023-11-16_105755.jpg': Barcode(
                code='4030521749429', 
                type='EAN13', 
                orientation='UP'
            )
        }
        
        examples_path=ScanWebServer.examples_path()
        root_path=f"{examples_path}/barcodes"
        barcode_files=os.listdir(root_path)
        barcodes={}
        debug=self.debug
        #debug=True
        for index, barcode_file in enumerate(barcode_files):
            barcode_path = f"{root_path}/{barcode_file}"
            barcode_list = Barcode.decode(barcode_path)
            self.assertEqual(len(barcode_list), 1, f"No barcodes found in {barcode_file}")
            decoded_barcode = barcode_list[0]
            barcodes[barcode_file]=decoded_barcode
            print(f"{index+1}:{barcode_file}{decoded_barcode}")
        for barcode_file,barcode in barcodes.items():
            if barcode_file in expected_dict:
                expected=expected_dict[barcode_file]
                self.assertEqual(decoded_barcode.code, expected.code, f"EAN number does not match for {barcode_file}")
                self.assertEqual(decoded_barcode.type, expected.type, f"EAN type does not match for {barcode_file}")
                self.assertEqual(decoded_barcode.orientation, expected.orientation, f"Orientation does not match for {barcode_file}")
