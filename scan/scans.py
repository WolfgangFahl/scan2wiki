"""
Created on 2023-11-14

@author: wf
"""

import os
from datetime import datetime
from typing import Any, Dict, List

from ngwidgets.widgets import Link

from scan.dms import Document
from scan.logger import Logger


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

    def get_scan_files(
        self, allowed_extensions: List[str] = [".pdf", ".jpg"]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the scanned files information from the directory.

        Args:
            allowed_extensions: List of file extensions to include. Defaults to [".pdf", ".jpg"]

        Returns:
            List[Dict[str, object]]: A list of dictionaries, each representing a file.
            Each dictionary contains details like file name, last modified time, size, and links for
            delete and upload actions, plus cache text file info if available.
        """
        scan_files = []

        for index, path in enumerate(self.get_valid_files(allowed_extensions)):
            try:
                scan_file = self.get_file_row(path, index)
                scan_files.append(scan_file)
            except Exception as ex:
                msg = f"error {str(ex)} for {path}"
                Logger.log(msg)
        scan_files = sorted(scan_files, key=lambda x: x["lastModified"], reverse=True)
        for index, scan_file in enumerate(scan_files):
            scan_file["#"] = index + 1
        return scan_files

    def get_valid_files(self, allowed_extensions: List[str]) -> List[str]:
        """
        Get list of valid files from scan directory that match allowed extensions.

        Args:
            allowed_extensions: List of file extensions to include

        Returns:
            List of valid filenames
        """
        valid_files = []

        for path in os.listdir(self.scandir):
            # Ignore hidden files
            if path.startswith("."):
                continue

            # Check file extension
            _, extension = os.path.splitext(path)
            if allowed_extensions and extension.lower() not in allowed_extensions:
                continue

            valid_files.append(path)

        return valid_files

    def get_file_row(self, path: str, index: int) -> Dict[str, Any]:
        """
        Create a dictionary entry for a single file with all metadata.

        Args:
            path: The filename
            index: The current index number

        Returns:
            Dictionary with file metadata
        """
        doc = Document()
        doc.fromFile(self.scandir, path, local=True, withOcr=True)

        fileurl, file_link = self.get_file_link(path)

        text_filename = f"{doc.baseName}.txt"
        text_path = self.get_full_path(text_filename)

        text_link = ""
        text_size = 0
        text_head = ""

        if os.path.exists(text_path):
            text_size = os.path.getsize(text_path)
            text_url, text_link = self.get_file_link(text_filename)
            text_head = doc.get_text_head(3)

        scan_file = {
            "#": index + 1,
            "name": file_link,
            "size": doc.size,
            "textLink": text_link,
            "textSize": text_size,
            "textHead": text_head,
            "lastModified": doc.timestampStr,
            "delete": Link.create(url=f"/delete/{path}", text="❌"),
            "upload": Link.create(url=f"/upload/{path}", text="⇧"),
            "pagetitle": doc.pageTitle,
            "wiki": "scan",
            "categories": doc.categories,
            "topic": doc.topic,
        }

        return scan_file

    def get_file_stats(self, fullpath: str, path: str) -> Dict[str, Any]:
        """
        Get basic stats for a file including modified time and size.

        Args:
            fullpath: Full path to the file
            path: Filename only

        Returns:
            Dictionary with file stats
        """
        ftime = datetime.fromtimestamp(os.path.getmtime(fullpath))
        ftimestr = ftime.strftime("%Y-%m-%d %H:%M:%S")
        size = os.path.getsize(fullpath)
        fileurl, file_link = self.get_file_link(path)

        return {
            "modified_time": ftimestr,
            "size": size,
            "file_url": fileurl,
            "file_link": file_link,
        }

    def delete(self, path: str):
        """
        Args:
            path (str): the file to delete
        """
        fullpath = self.get_full_path(path)
        os.remove(fullpath)
