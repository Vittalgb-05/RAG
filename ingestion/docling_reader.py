"""Structured document layout and markdown table extraction using Docling.

Integrates Docling's DocumentConverter with CPU-only pipeline (do_ocr=False,
do_table_structure=True) to recover reading order, headings, and markdown tables.
Degrades gracefully to PdfReader (pypdf) if docling is missing or encounters
conversion failures.
"""

from collections import defaultdict
import hashlib
import io
import logging
import os
from pathlib import Path
import re
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.models import Chunk, Page
from ingestion.pdf_reader import PdfReader

logger = logging.getLogger(__name__)

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
        self.fallback_used: bool = False

    @staticmethod
    def _split_table_markdown(table_md: str, max_chars: int = 1800) -> list[str]:
        """Split a long markdown table into row-group chunks, repeating the header.

        Tables longer than the previous 2,000-character threshold were routed through
        the prose splitter, which cut rows arbitrarily and lost the header.  Each
        returned chunk contains the header + separator so it remains interpretable.

        Args:
            table_md: Markdown table text.
            max_chars: Maximum characters per output chunk.

        Returns:
            List of markdown table chunks (at least one).
        """
        lines = [ln for ln in table_md.splitlines() if ln.strip()]
        if len(lines) <= 2:
            return [table_md.strip()] if table_md.strip() else []

        header: list[str] = []
        body_start = 0
        if len(lines) >= 2 and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[1]):
            header = lines[:2]
            body_start = 2
        elif lines[0].lstrip().startswith("|"):
            header = [lines[0]]
            body_start = 1

        prefix = "\n".join(header)
        chunks: list[str] = []
        current: list[str] = []
        current_len = len(prefix)

        for row in lines[body_start:]:
            if current and current_len + len(row) + 1 > max_chars:
                chunks.append("\n".join(header + current))
                current = [row]
                current_len = len(prefix) + len(row) + 1
            else:
                current.append(row)
                current_len += len(row) + 1

        if current:
            chunks.append("\n".join(header + current))
        return chunks or [table_md.strip()]

    @staticmethod
    def _export_table_markdown(table_obj: Any, doc: Any = None) -> str:
        """Safely export a table to markdown, supplying parent doc to suppress deprecation warnings."""
        if not hasattr(table_obj, "export_to_markdown"):
            return ""
        try:
            if doc is not None:
                try:
                    return str(table_obj.export_to_markdown(doc=doc) or "")
                except TypeError:
                    return str(table_obj.export_to_markdown() or "")
            return str(table_obj.export_to_markdown() or "")
        except Exception:
            return ""

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
        raw_hash = (
            hashlib.sha256(self._raw_bytes).hexdigest()
            if self._raw_bytes
            else hashlib.sha256(self.filename.encode("utf-8")).hexdigest()
        )
        effective_doc_id = doc_id or f"doc_{raw_hash[:16]}"
        chunk_prefix = sha12 or raw_hash[:12]

        if not self._has_docling:
            logger.info("docling package missing; using PdfReader fallback for %s.", self.filename)
            self.fallback_used = True
            self.pages_text = self._fallback_reader.extract_text(doc_id=effective_doc_id, sha12=chunk_prefix)
            self.page_chunks = self._fallback_reader.get_paragraphs()
            self.page_records = self._fallback_reader.get_page_records()
            return self.pages_text

        try:
            if self._converter is None:
                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = False
                pipeline_options.do_table_structure = True
                # Pin layout/table models to CPU.  Docling defaults to accelerator
                # "auto" and would otherwise compete with llama-server for the 4 GB
                # VRAM budget during ingestion.
                try:
                    from docling.datamodel.pipeline_options import AcceleratorDevice

                    pipeline_options.accelerator_options.device = AcceleratorDevice.CPU
                except (ImportError, AttributeError) as accel_err:
                    logger.debug("Could not pin Docling accelerator to CPU: %s", accel_err)

                # Optional local artifact directory for fully offline deployments.
                # First run without pre-downloaded artifacts will fetch models from
                # the HuggingFace cache/network; this is a model download, never
                # document content egress, and is documented in docs/RUNBOOK.md.
                artifacts_path = os.environ.get("DOCLING_ARTIFACTS_PATH")
                if artifacts_path:
                    pipeline_options.artifacts_path = artifacts_path

                self._converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
                )

            if DocumentStream is not None:
                stream = DocumentStream(name=self.filename, stream=io.BytesIO(self._raw_bytes))
            else:
                stream = io.BytesIO(self._raw_bytes)
            conv_res = self._converter.convert(stream)
            docling_doc = conv_res.document

            # Group items by page preserving sequential reading order (CR-03)
            page_items: dict[int, list[str]] = defaultdict(list)

            # Extract items in natural document sequence
            if hasattr(docling_doc, "iterate_items"):
                for item, _level in docling_doc.iterate_items():
                    page_no = 1
                    if hasattr(item, "prov") and item.prov:
                        page_no = getattr(item.prov[0], "page_no", 1)

                    # Check if item is a TableItem with markdown export
                    if hasattr(item, "export_to_markdown"):
                        try:
                            table_md = self._export_table_markdown(item, doc=docling_doc)
                            if table_md and table_md.strip():
                                page_items[page_no].append(table_md.strip())
                                continue
                        except Exception:
                            pass
                    elif "table" in str(getattr(item, "label", "")).lower():
                        table_exported = False
                        if hasattr(docling_doc, "tables"):
                            for t in docling_doc.tables:
                                t_page = getattr(t.prov[0], "page_no", 1) if hasattr(t, "prov") and t.prov else 1
                                if t_page == page_no and hasattr(t, "export_to_markdown"):
                                    t_md = self._export_table_markdown(t, doc=docling_doc)
                                    if t_md and t_md.strip() and t_md.strip() not in page_items[page_no]:
                                        page_items[page_no].append(t_md.strip())
                                        table_exported = True
                                        break
                        if table_exported:
                            continue

                    text = getattr(item, "text", "")
                    if text and text.strip():
                        page_items[page_no].append(text.strip())

            # Ensure any tables in docling_doc.tables not yet captured are appended
            if hasattr(docling_doc, "tables"):
                for table in docling_doc.tables:
                    page_no = 1
                    if hasattr(table, "prov") and table.prov:
                        page_no = getattr(table.prov[0], "page_no", 1)
                    table_md = self._export_table_markdown(table, doc=docling_doc)
                    if table_md and table_md.strip() and table_md.strip() not in page_items[page_no]:
                        page_items[page_no].append(table_md.strip())

            # Fallback to export_to_markdown if iterate_items was absent
            if not page_items and hasattr(docling_doc, "export_to_markdown"):
                md_full = docling_doc.export_to_markdown()
                if md_full and md_full.strip():
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
                logger.info(
                    "No items extracted by docling for %s; falling back to PdfReader.",
                    self.filename,
                )
                self.fallback_used = True
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
                current_offset = 0

                # Group consecutive non-table items into coherent blocks
                blocks: list[tuple[str, bool]] = []  # (content, is_table)
                text_group: list[str] = []

                def flush_group() -> None:
                    if text_group:
                        blocks.append(("\n\n".join(text_group).strip(), False))
                        text_group.clear()

                for item in items:
                    item_str = item.strip()
                    if not item_str:
                        continue
                    if item_str.startswith("|"):
                        flush_group()
                        for table_piece in self._split_table_markdown(item_str):
                            if table_piece.strip():
                                blocks.append((table_piece.strip(), True))
                    else:
                        text_group.append(item_str)

                flush_group()

                for block_content, is_tbl in blocks:
                    if is_tbl:
                        item_start = page_text.find(block_content, current_offset)
                        if item_start == -1:
                            item_start = min(current_offset, len(page_text))
                        item_end = min(len(page_text), item_start + len(block_content))
                        current_offset = item_end

                        chunk_id = f"{chunk_prefix}_p{page_num}_{chunk_index:04d}"
                        chunk_model = Chunk(
                            content=block_content,
                            filename=self.filename,
                            page=page_num,
                            chunk_id=chunk_id,
                            doc_id=effective_doc_id,
                            char_start=item_start,
                            char_end=item_end,
                            extraction="docling",
                        )
                        self.page_chunks.append(chunk_model.model_dump())
                        page_chunks_added += 1
                        chunk_index += 1
                    else:
                        sub_chunks = text_splitter.split_text(block_content)
                        # Resolve the block's absolute position once, then map each
                        # splitter chunk relative to it. Searching page_text again for
                        # every chunk repeatedly missed overlapping chunks and could
                        # leave current_offset stuck at end-of-page.
                        block_start = page_text.find(block_content, current_offset)
                        if block_start == -1:
                            block_start = min(current_offset, len(page_text))
                        local_cursor = 0
                        for sc in sub_chunks:
                            content = sc.strip()
                            if not content:
                                continue
                            local_start = block_content.find(content, local_cursor)
                            if local_start == -1:
                                local_start = local_cursor
                            local_end = min(len(block_content), local_start + len(content))
                            sc_start = min(len(page_text), block_start + local_start)
                            sc_end = min(len(page_text), block_start + local_end)
                            # Chunks overlap by design (chunk_overlap=200); advance the
                            # local cursor by one character so the next overlapping
                            # chunk resolves its own (still monotonic) start.
                            local_cursor = local_start + 1

                            chunk_id = f"{chunk_prefix}_p{page_num}_{chunk_index:04d}"
                            chunk_model = Chunk(
                                content=content,
                                filename=self.filename,
                                page=page_num,
                                chunk_id=chunk_id,
                                doc_id=effective_doc_id,
                                char_start=sc_start,
                                char_end=sc_end,
                                extraction="docling",
                            )
                            self.page_chunks.append(chunk_model.model_dump())
                            page_chunks_added += 1
                            chunk_index += 1

                        current_offset = min(len(page_text), block_start + len(block_content))

                self.page_records.append(
                    Page(
                        doc_id=effective_doc_id,
                        page_num=page_num,
                        status="ok" if page_chunks_added > 0 else "empty",
                        char_count=len(page_text),
                        error=None,
                        num_chunks=page_chunks_added,
                        page_text=page_text,
                    )
                )

            self.pages_text = "\n\n".join(all_pages_text)
            logger.info(
                "Successfully extracted structured text from %s. Chunks: %d",
                self.filename,
                len(self.page_chunks),
            )
            return self.pages_text

        except Exception as err:
            logger.warning("Conversion error (%s); falling back to PdfReader.", err)
            self.fallback_used = True
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
