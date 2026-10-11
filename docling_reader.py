"""Structured document layout and markdown table extraction using Docling.

Integrates Docling's DocumentConverter with CPU-only pipeline (do_ocr=False,
do_table_structure=True) to recover reading order, headings, and markdown tables.
Degrades gracefully to PdfReader (pypdf) if docling is missing or encounters
conversion failures.
"""

from collections import defaultdict
import io
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from models import Chunk, Page
from pdf_reader import PdfReader

try:
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
except ImportError:
    DocumentConverter = None  # type: ignore[assignment, misc]
    DocumentStream = None  # type: ignore[assignment, misc]
    InputFormat = None  # type: ignore[assignment, misc]
    PdfPipelineOptions = None  # type: ignore[assignment, misc]
    PdfFormatOption = None  # type: ignore[assignment, misc]


class DoclingReader:
    """Extracts structured text, headings, and markdown tables using Docling."""

    def __init__(
        self,
        file_or_path: Any,
        filename: str | None = None,
        converter: Any = None,
    ) -> None:
        """Initialize DoclingReader.

        Args:
            file_or_path: Path, filename string, io.BytesIO, or bytes buffer.
            filename: Optional explicit filename.
            converter: Optional pre-configured DocumentConverter instance.
        """
        if isinstance(file_or_path, (str, Path)):
            self.filename = filename or Path(file_or_path).name
            with open(file_or_path, "rb") as f:
                self._raw_bytes = f.read()
        elif hasattr(file_or_path, "getvalue"):
            self.filename = filename or getattr(file_or_path, "name", "unknown.pdf")
            self._raw_bytes = file_or_path.getvalue()
        elif hasattr(file_or_path, "read"):
            self.filename = filename or getattr(file_or_path, "name", "unknown.pdf")
            pos = file_or_path.tell() if hasattr(file_or_path, "tell") else 0
            self._raw_bytes = file_or_path.read()
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(pos)
        elif isinstance(file_or_path, bytes):
            self.filename = filename or "unknown.pdf"
            self._raw_bytes = file_or_path
        else:
            self.filename = filename or "unknown.pdf"
            self._raw_bytes = b""

        self._has_docling = DocumentConverter is not None
        self._converter = converter
        self._fallback_reader = PdfReader(io.BytesIO(self._raw_bytes), filename=self.filename)

        self.pages_text = ""
        self.page_chunks: list[dict[str, Any]] = []
        self.page_records: list[Page] = []

    def extract_text(
        self,
        doc_id: str | None = None,
        sha12: str | None = None,
    ) -> str:
        """Extract structured text and markdown tables into chunks and page records.

        Args:
            doc_id: Canonical document identifier (e.g. doc_<sha16>).
            sha12: 12-character SHA prefix for stable chunk IDs.

        Returns:
            Concatenated extracted document text.
        """
        effective_doc_id = doc_id or f"doc_{self.filename}"
        chunk_prefix = sha12 if sha12 else self.filename

        if not self._has_docling:
            print(f"[DoclingReader] docling package missing; using PdfReader fallback for {self.filename}.")
            self.pages_text = self._fallback_reader.extract_text(doc_id=effective_doc_id, sha12=chunk_prefix)
            self.page_chunks = self._fallback_reader.get_paragraphs()
            self.page_records = self._fallback_reader.get_page_records()
            return self.pages_text

        try:
            if self._converter is None:
                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = False
                pipeline_options.do_table_structure = True
                self._converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
                )

            if DocumentStream is not None:
                stream = DocumentStream(name=self.filename, stream=io.BytesIO(self._raw_bytes))
            else:
                stream = io.BytesIO(self._raw_bytes)
            conv_res = self._converter.convert(stream)
            docling_doc = conv_res.document

            # Group items by page
            page_items: dict[int, list[str]] = defaultdict(list)

            # Extract markdown tables and items
            if hasattr(docling_doc, "tables"):
                for table in docling_doc.tables:
                    page_no = 1
                    if hasattr(table, "prov") and table.prov:
                        page_no = getattr(table.prov[0], "page_no", 1)
                    table_md = table.export_to_markdown() if hasattr(table, "export_to_markdown") else ""
                    if table_md.strip():
                        page_items[page_no].append(table_md.strip())

            # Extract text elements and headings
            if hasattr(docling_doc, "iterate_items"):
                for item, _level in docling_doc.iterate_items():
                    item_type = getattr(item, "label", "")
                    if "table" in str(item_type).lower():
                        # Already handled via tables
                        continue
                    text = getattr(item, "text", "")
                    if not text:
                        continue
                    page_no = 1
                    if hasattr(item, "prov") and item.prov:
                        page_no = getattr(item.prov[0], "page_no", 1)
                    page_items[page_no].append(text.strip())
            else:
                # Fallback to export_to_markdown if iterate_items is unavailable
                md_full = docling_doc.export_to_markdown() if hasattr(docling_doc, "export_to_markdown") else ""
                if md_full.strip():
                    page_items[1].append(md_full.strip())

            # Text splitter for prose within pages
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )

            self.page_chunks = []
            self.page_records = []
            all_pages_text: list[str] = []

            # If no items were extracted, fallback
            if not page_items:
                print(f"[DoclingReader] No items extracted by docling for {self.filename}; falling back to PdfReader.")
                self.pages_text = self._fallback_reader.extract_text(doc_id=effective_doc_id, sha12=chunk_prefix)
                self.page_chunks = self._fallback_reader.get_paragraphs()
                self.page_records = self._fallback_reader.get_page_records()
                return self.pages_text

            num_pages = len(docling_doc.pages) if hasattr(docling_doc, "pages") else 0
            total_pages = max(num_pages, max(page_items.keys(), default=1))

            for page_num in range(1, total_pages + 1):
                items = page_items.get(page_num, [])
                if not items:
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

                page_text = "\n\n".join(items)
                all_pages_text.append(page_text)

                page_chunks_added = 0
                chunk_index = 0
                for item in items:
                    # If item is a markdown table (starts with |), keep intact if reasonable length
                    if item.startswith("|") and len(item) <= 2000:
                        chunk_id = f"{chunk_prefix}_p{page_num}_{chunk_index:04d}"
                        chunk_model = Chunk(
                            content=item,
                            filename=self.filename,
                            page=page_num,
                            chunk_id=chunk_id,
                            doc_id=effective_doc_id,
                            extraction="docling",
                        )
                        self.page_chunks.append(chunk_model.model_dump())
                        page_chunks_added += 1
                        chunk_index += 1
                    else:
                        sub_chunks = text_splitter.split_text(item)
                        for sc in sub_chunks:
                            content = sc.strip()
                            if not content:
                                continue
                            chunk_id = f"{chunk_prefix}_p{page_num}_{chunk_index:04d}"
                            chunk_model = Chunk(
                                content=content,
                                filename=self.filename,
                                page=page_num,
                                chunk_id=chunk_id,
                                doc_id=effective_doc_id,
                                extraction="docling",
                            )
                            self.page_chunks.append(chunk_model.model_dump())
                            page_chunks_added += 1
                            chunk_index += 1

                self.page_records.append(
                    Page(
                        doc_id=effective_doc_id,
                        page_num=page_num,
                        status="ok" if page_chunks_added > 0 else "empty",
                        char_count=len(page_text),
                        error=None,
                        num_chunks=page_chunks_added,
                    )
                )

            self.pages_text = "\n\n".join(all_pages_text)
            print(
                f"[DoclingReader] Successfully extracted structured text from {self.filename}. Chunks: {len(self.page_chunks)}"
            )
            return self.pages_text

        except Exception as err:
            print(f"[DoclingReader] Conversion error ({err}); falling back to PdfReader.")
            self.pages_text = self._fallback_reader.extract_text(doc_id=effective_doc_id, sha12=chunk_prefix)
            self.page_chunks = self._fallback_reader.get_paragraphs()
            self.page_records = self._fallback_reader.get_page_records()
            return self.pages_text

    def get_paragraphs(self) -> list[dict[str, Any]]:
        """Return list of chunk dictionaries for vector indexing."""
        if not self.page_chunks:
            self.extract_text()
        return self.page_chunks

    def get_page_records(self) -> list[Page]:
        """Return list of canonical Page records."""
        if not self.page_records:
            self.extract_text()
        return self.page_records

    def extract_small_portion_of_the_pdf(self, min_idx: int = 0, max_idx: int | None = None) -> str:
        """Return a slice of the extracted text."""
        if not self.pages_text:
            self.extract_text()
        return self.pages_text[min_idx:max_idx]
