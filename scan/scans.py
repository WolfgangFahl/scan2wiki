"""
Created on 2023-11-14

@author: wf
"""

import os
from datetime import datetime
from typing import Dict, List

from ngwidgets.widgets import Link


class Scans:
    """
    Class to handle operations related to scanned files.
    """

    def __init__(self, scandir: str):
        """
        Initialize the Scans object.

        Args:
            scandir (str): The directory where the scanned files are located.
        """
        self.scandir = scandir

    def get_full_path(self, path: str) -> str:
        """
        Generate the full path for a given relative path.

        Args:
            path (str): The relative path to be resolved.

        Returns:
            str: The full path combining the scandir and the provided relative path.
        """
        fullpath = os.path.join(self.scandir, path)
        return fullpath

    def get_file_link(self, path: str) -> str:
        """
        get a link to the given file

        Args:
            path (str) the path to the file

        Returns:
            str: The html markup for the RESTFul API to show the file
        """
        url = f"/files/{path}"
        link = Link.create(url, text=path)
        return url, link

    def get_scan_files(self) -> List[Dict[str, object]]:
        """
        Retrieve the scanned files information from the directory.

        Returns:
            List[Dict[str, object]]: A list of dictionaries, each representing a file.
            Each dictionary contains details like file name, last modified time, size, and links for delete and upload actions.
        """
        scan_files = []
        for index, path in enumerate(os.listdir(self.scandir)):
            try:
                # ignore .smbdelete and similar files
                if path.startswith('.' ):
                    continue
                fullpath = self.get_full_path(path)
                ftime = datetime.fromtimestamp(os.path.getmtime(fullpath))
                ftimestr = ftime.strftime("%Y-%m-%d %H:%M:%S")
                size = os.path.getsize(fullpath)
                _file_url, file_link = self.get_file_link(path)
                current_date = datetime.now()
                scan_file = {
                    "#": index + 1,
                    "name": file_link,
                    "lastModified": ftimestr,
                    "delete": Link.create(url=f"/delete/{path}", text="❌"),
                    "upload": Link.create(url=f"/upload/{path}", text="⇧"),
                    "size": size,
                    "pagetitle": "",
                    "wiki": "scan",
                    "categories": str(current_date.year),
                    "topic": "OCRDocument",
                }
                scan_files.append(scan_file)
            except Exception as ex:
                msg = f"error {str(ex)} for {path}"
                raise Exception(msg)
        scan_files = sorted(scan_files, key=lambda x: x['lastModified'],reverse=True)
        for index,scan_file in enumerate(scan_files):
            scan_file["#"]=index+1
        return scan_files

    def delete(self, path:str):
        """
        Args:
            path (str): the file to delete
        """
        fullpath = self.get_full_path(path)
        os.remove(fullpath)
