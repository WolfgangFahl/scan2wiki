# derived from
# https://stackoverflow.com/a/26351413/1497139

from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from io import StringIO

class PDFMiner:
    '''
    PDFMiner wrapper to get PDF Text
    '''

    @classmethod
    def getPDFText(cls,pdfFilenamePath,throwError:bool=True):
        retstr = StringIO()
        parser = PDFParser(open(pdfFilenamePath,'rb'))
        try:
            document = PDFDocument(parser)
        except Exception as e:
            errMsg=f"error {pdfFilenamePath}:{str(e)}"
            print(errMsg)
            if throwError:
                raise e
            return ''
        if document.is_extractable:
            rsrcmgr = PDFResourceManager()
            device = TextConverter(rsrcmgr,retstr,  laparams = LAParams())
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            for page in PDFPage.create_pages(document):
                interpreter.process_page(page)
            return retstr.getvalue()
        else:
            print(pdfFilenamePath,"Warning: could not extract text from pdf file.")
            return ''