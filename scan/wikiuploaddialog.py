'''
Created on 2021-03-21

@author: wf
'''

import tkinter as tk

from tkinter import ttk
from scan.uploadentry import UploadEntry

class WikiUploadDialog(object):
    '''
    wiki configuration dialog
    '''

    def __init__(self,wikiUsers):
        '''
        Constructor
        '''
        self.wikiUsers=wikiUsers
        self.top = tk.Tk()
        self.top.title("Upload scanned Files to wiki")
        self.top.configure(width=640, height=480)
        
    def show(self,files,callback):
        
        def doUpload():
            for i,file in enumerate(files):
                if file:
                    uploadEntry=uploadEntries[i]
                    uploadEntry.fromTk()
                    callback(wikiSelect.get(),uploadEntry)
            
        wikiIds=[]
        for wikiId in self.wikiUsers.keys():
            wikiIds.append(wikiId)
        wikiIds=sorted(wikiIds)
        row=0
        uploadButton = tk.Button(self.top, text="Upload", command=doUpload)
        uploadButton.grid(column=0,row=row)
        row=row+1
        
        wikiSelect=ttk.Combobox(self.top, 
                            values=wikiIds)
        wikiSelect.current(0)
        wikiSelect.grid(column=0, row=row)
        
        uploadEntries=[]
        for i,file in enumerate(files):
            uploadEntry=UploadEntry(i,file)
            uploadEntry.add2Tk(self.top,row+1)
            uploadEntries.append(uploadEntry)
         
        self.top.mainloop()
        
        

        
        