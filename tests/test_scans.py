"""
Created on 2023-11-14

@author: wf
"""
import os
import shutil
from scan.scans import Scans
from ngwidgets.basetest import Basetest

class TestScans(Basetest):
    """
    test the Scans class
    """
    
    def setUp(self, debug=False, profile=True):
        """
        create a few files for testing
        """
        Basetest.setUp(self, debug=debug, profile=profile)
        self.test_dir = '/tmp/scans_test'
        os.makedirs(self.test_dir, exist_ok=True)
        # Create some test files
        for i in range(3):
            with open(os.path.join(self.test_dir, f'test_file_{i}.txt'), 'w') as f:
                f.write(f'This is test file {i}')
                
    def tearDown(self):
        """
        Clean up after tests.
        """
        Basetest.tearDown(self)
        shutil.rmtree(self.test_dir)
        
    def test_get_full_path(self):
        """
        Test the get_full_path method.
        """
        scans = Scans(self.test_dir)
        path = 'test_file_1.txt'
        expected = os.path.join(self.test_dir, path)
        self.assertEqual(scans.get_full_path(path), expected)

    def test_get_scan_files(self):
        """
        Test the get_scan_files method.
        """
        scans = Scans(self.test_dir)
        scan_files = scans.get_scan_files()
        self.assertEqual(len(scan_files), 3)
        # Add more assertions to check the contents of scan_files

    def test_delete(self):
        """
        Test the delete method.
        """
        scans = Scans(self.test_dir)
        path = 'test_file_2.txt'
        scans.delete(path)
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, path)))