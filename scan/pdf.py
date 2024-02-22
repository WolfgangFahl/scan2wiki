# derived from
# https://stackoverflow.com/a/26351413/1497139

from io import StringIO

from pdfminer.converter import TextConverter
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser


class PDFMiner:
    """
    PDFMiner.six wrapper to get PDF Text
    """

    @classmethod
    def getPDFText(cls, pdfFilenamePath, throwError: bool = True):
        retstr = StringIO()
        parser = PDFParser(open(pdfFilenamePath, "rb"))
        try:
            document = PDFDocument(parser)
        except Exception as e:
            errMsg = f"error {pdfFilenamePath}:{str(e)}"
            print(errMsg)
            if throwError:
                raise e
            return ""
        if document.is_extractable:
            rsrcmgr = PDFResourceManager()
            device = TextConverter(rsrcmgr, retstr, laparams=LAParams())
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            for page in PDFPage.create_pages(document):
                interpreter.process_page(page)
            return retstr.getvalue()
        else:
            print(pdfFilenamePath, "Warning: could not extract text from pdf file.")
            return ""
