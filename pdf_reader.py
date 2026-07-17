import re
import pypdf


from langchain_text_splitters import RecursiveCharacterTextSplitter

class PdfReader:
    
    # initializing our pdf reader class
    def __init__(self, file_or_path, filename=None):
        '''
            starting our class Reader which has to take the Path of the pdf we want to read
        '''
        self.reader = pypdf.PdfReader(file_or_path)
        # default to the basename of the path if no filename is provided
        if filename:
            self.filename = filename
        elif isinstance(file_or_path, str):
            self.filename = file_or_path.split('/')[-1].split('\\')[-1]
        else:
            self.filename = getattr(file_or_path, 'name', 'unknown.pdf')
        self.pages_text = ""
        self.page_chunks = []

    # extracting from pdf to text
    def extract_text(self):
        '''
            extracting the pages of the pdf into a string that we can later use as we wish,
            while building a list of chunk dictionaries that track page number and filename.
        '''
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        
        all_pages_text = []
        for i, page in enumerate(self.reader.pages):
            page_num = i + 1
            page_text = page.extract_text()
            if page_text:  
                # Clean up multiple spaces and weird newlines first
                pdf_text = re.sub(r' +', ' ', page_text)
                
                all_pages_text.append(pdf_text)
                
                # Split into chunks using langchain and store with metadata
                chunks = text_splitter.split_text(pdf_text)
                for j, p in enumerate(chunks):
                    chunk_id = f"{self.filename}_p{page_num}_{j}"
                    self.page_chunks.append({
                        "content": p.strip(),
                        "filename": self.filename,
                        "page": page_num,
                        "chunk_id": chunk_id
                    })

        # Join the text from all pages for backward compatibility
        self.pages_text = "\n".join(all_pages_text)
        print(f"Successfully extracted text from {self.filename}. Total characters: {len(self.pages_text)}")
        return self.pages_text

    def extract_small_portion_of_the_pdf(self, min=0, max=None):
        '''
            showing a portion of the book to allow the user to see what it looks like
        '''
        if self.pages_text == "":
            self.extract_text() 
        return self.pages_text[min:max]
    
    def get_paragraphs(self):                                                       
        '''                                                                         
            returns a list of dictionaries (with chunk metadata) extracted from the pdf text.               
            call extract_text() first before using this method.                     
        '''
        if not self.page_chunks:
            self.extract_text()                                                                         
        return self.page_chunks 


###############
# example to Run to make sure the class is good
###############

#pdf_reader = PdfReader(path="./pdfs/2025-q1-earnings-transcript.pdf")
#pdf_reader.extract_text()
#print(pdf_reader.extract_small_portion_of_the_pdf(max=10000))
#print(pdf_reader.get_paragraphs()[:3])
