import hashlib
from pathlib import Path
import re
import pypdf

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.models import Chunk, Page


class PdfReader:
    # initializing our pdf reader class
    def __init__(self, file_or_path, filename=None):
        """
        starting our class Reader which has to take the Path of the pdf we want to read
        """
        self.reader = pypdf.PdfReader(file_or_path)
        # default to the basename of the path if no filename is provided
        if filename:
            self.filename = filename
        elif isinstance(file_or_path, (str, Path)):
            self.filename = Path(file_or_path).name
        else:
            self.filename = getattr(file_or_path, "name", "unknown.pdf")

        self._sha256 = None
        try:
            if isinstance(file_or_path, (str, Path)):
                p = Path(file_or_path)
                if p.exists() and p.is_file():
                    self._sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
            elif hasattr(file_or_path, "getvalue"):
                self._sha256 = hashlib.sha256(file_or_path.getvalue()).hexdigest()
            elif hasattr(file_or_path, "seek") and hasattr(file_or_path, "read"):
                pos = file_or_path.tell()
                self._sha256 = hashlib.sha256(file_or_path.read()).hexdigest()
                file_or_path.seek(pos)
        except Exception:
            self._sha256 = None

        self.pages_text = ""
        self.page_chunks = []
        self.page_records: list[Page] = []

    # extracting from pdf to text
    def extract_text(self, doc_id: str | None = None, sha12: str | None = None):
        """
        extracting the pages of the pdf into a string that we can later use as we wish,
        while building a list of chunk dictionaries that track page number and filename.
        Supports page fault isolation and hash-based chunk ID prefixes.
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

        fallback_hash = self._sha256 or hashlib.sha256(self.filename.encode("utf-8")).hexdigest()
        effective_doc_id = doc_id or f"doc_{fallback_hash[:16]}"
        chunk_prefix = sha12 if sha12 else self.filename

        self.page_chunks = []
        self.page_records = []
        all_pages_text = []

        for i, page in enumerate(self.reader.pages):
            page_num = i + 1
            try:
                page_text = page.extract_text()
                if not page_text or not page_text.strip():
                    self.page_records.append(
                        Page(
                            doc_id=effective_doc_id,
                            page_num=page_num,
                            status="empty",
                            char_count=0,
                            error=None,
                            num_chunks=0,
                        )
                    )
                    continue

                # Clean up multiple spaces and weird newlines first
                pdf_text = re.sub(r" +", " ", page_text)
                all_pages_text.append(pdf_text)

                # Split into chunks using langchain and store with metadata
                chunks = text_splitter.split_text(pdf_text)
                page_chunks_added = 0
                for j, p in enumerate(chunks):
                    content = p.strip()
                    if not content:
                        continue
                    chunk_id = f"{chunk_prefix}_p{page_num}_{j:04d}"
                    chunk_model = Chunk(
                        content=content,
                        filename=self.filename,
                        page=page_num,
                        chunk_id=chunk_id,
                        doc_id=effective_doc_id,
                        extraction="pypdf",
                    )
                    self.page_chunks.append(chunk_model.model_dump())
                    page_chunks_added += 1

                self.page_records.append(
                    Page(
                        doc_id=effective_doc_id,
                        page_num=page_num,
                        status="ok" if page_chunks_added > 0 else "empty",
                        char_count=len(pdf_text),
                        error=None,
                        num_chunks=page_chunks_added,
                    )
                )
            except Exception as err:
                self.page_records.append(
                    Page(
                        doc_id=effective_doc_id,
                        page_num=page_num,
                        status="failed",
                        char_count=0,
                        error=str(err),
                        num_chunks=0,
                    )
                )
                continue

        # Join the text from all pages for backward compatibility
        self.pages_text = "\n".join(all_pages_text)
        print(f"Successfully extracted text from {self.filename}. Total characters: {len(self.pages_text)}")
        return self.pages_text

    def extract_small_portion_of_the_pdf(self, min=0, max=None):
        """
        showing a portion of the book to allow the user to see what it looks like
        """
        if self.pages_text == "":
            self.extract_text()
        return self.pages_text[min:max]

    def get_paragraphs(self):
        """
        returns a list of dictionaries (with chunk metadata) extracted from the pdf text.
        call extract_text() first before using this method.
        """
        if not self.page_chunks:
            self.extract_text()
        return self.page_chunks

    def get_page_records(self) -> list[Page]:
        """
        returns a list of Page record models tracking extraction status per page.
        """
        if not self.page_records and self.reader.pages:
            self.extract_text()
        return self.page_records


###############
# example to Run to make sure the class is good
###############

# pdf_reader = PdfReader(path="./pdfs/2025-q1-earnings-transcript.pdf")
# pdf_reader.extract_text()
# print(pdf_reader.extract_small_portion_of_the_pdf(max=10000))
# print(pdf_reader.get_paragraphs()[:3])
