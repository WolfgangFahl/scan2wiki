"""
Created on 2025-04-07

@author: wf
"""

import os
import re

import fitz  # PyMuPDF


class PDFExtractor:
    """
    PyMuPDF wrapper to get PDF Text with caching capability
    """

    @classmethod
    def getPDFText(
        cls, pdfFilenamePath, throwError: bool = True, useCache: bool = True
    ):
        """
        Gets text content from PDF, with optional caching.

        Args:
            pdfFilenamePath: Path to the PDF file
            throwError: If True, raises exceptions instead of returning empty string
            useCache: If True, uses/creates a .txt cache file with the same base name

        Returns:
            str: The text content of the PDF
        """
        # Define the cache file path
        txt_cache_path = re.sub(r"\.pdf$", ".txt", pdfFilenamePath, flags=re.IGNORECASE)

        # If cache should be used and exists, read from it
        if useCache and os.path.exists(txt_cache_path):
            try:
                with open(txt_cache_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"Warning: Failed to read cache file {txt_cache_path}: {str(e)}")
                # Continue with PDF extraction if cache reading fails

        try:
            # Open the PDF file
            doc = fitz.open(pdfFilenamePath)

            # Extract text from all pages and join them
            text = ""
            for page in doc:
                text += page.get_text()

            # Close the document
            doc.close()

            # If caching is enabled, write the text to the cache file
            if useCache and text:
                try:
                    with open(txt_cache_path, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception as e:
                    print(
                        f"Warning: Failed to write cache file {txt_cache_path}: {str(e)}"
                    )

            return text

        except Exception as e:
            errMsg = f"error {pdfFilenamePath}:{str(e)}"
            print(errMsg)
            if throwError:
                raise e
            return ""
