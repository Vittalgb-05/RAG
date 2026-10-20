"""Ingestion service coordinating validation, extraction, OCR, visual analysis, and indexing."""

from dataclasses import dataclass
import datetime
import io
import json
import logging
from pathlib import Path
from typing import Any, Callable

from doc_store import DocStore
from docling_reader import DoclingReader
from hybrid_retriever import HybridRetriever
from local_embedding import LocalEmbedding
from models import Chunk, Document, EvidenceElement, Page, cache_dir_for
from ocr_fallback import apply_conditional_ocr
from upload_validation import validate_pdf_bytes
from visual_analyzer import VisualAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result container for document ingestion workflow."""

    success: bool
    doc_id: str
    filename: str
    sha256: str
    num_pages: int
    num_chunks: int
    fallback_used: bool = False
    error: str | None = None
    upload_time: str = ""


class IngestionService:
    """Orchestrates end-to-end PDF processing with fault isolation and atomic indexing."""

    def __init__(
        self,
        doc_store: DocStore,
        hybrid_retriever: HybridRetriever | None = None,
        local_embedding: LocalEmbedding | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.doc_store = doc_store
        self.retriever = hybrid_retriever
        self.embedding = local_embedding
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent.parent / ".cache")

    def ingest_pdf(
        self,
        raw_bytes: bytes,
        filename: str,
        vlm_provider: Any = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> IngestionResult:
        """Process and index a PDF file into SQLite and LanceDB.

        Args:
            raw_bytes: Raw binary content of the PDF.
            filename: Original uploaded filename.
            vlm_provider: Optional local VLM provider for figure/table understanding.
            progress_callback: Optional progress reporter for UI status widgets.

        Returns:
            IngestionResult with processing metadata and status.
        """

        def _report(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)
            logger.info("[%s] %s", filename, msg)

        # 1. Validation
        _report(f"Validating {filename}…")
        try:
            validated = validate_pdf_bytes(raw_bytes, filename)
        except Exception as val_err:
            return IngestionResult(
                success=False,
                doc_id="",
                filename=filename,
                sha256="",
                num_pages=0,
                num_chunks=0,
                error=f"Validation error: {val_err}",
            )

        doc_id = validated.doc_id
        sha256 = validated.sha256
        sha12 = sha256[:12]

        # 2. Deduplication check
        existing_doc = self.doc_store.get_by_sha(sha256)
        if existing_doc and existing_doc.status == "indexed" and existing_doc.num_chunks > 0:
            _report(f"Document already indexed as {doc_id}.")
            return IngestionResult(
                success=True,
                doc_id=doc_id,
                filename=existing_doc.filename or filename,
                sha256=sha256,
                num_pages=existing_doc.num_pages,
                num_chunks=existing_doc.num_chunks,
                upload_time=existing_doc.upload_time,
            )

        # 3. Extraction (Docling with automatic pypdf fallback)
        _report("Extracting text and document structure…")
        paragraphs: list[dict[str, Any]] = []
        page_records: list[Page] = []
        fallback_used = False

        try:
            pdf_stream = io.BytesIO(raw_bytes)
            docling_reader = DoclingReader(pdf_stream, filename=filename)
            docling_reader.extract_text(doc_id=doc_id, sha12=sha12)
            paragraphs = docling_reader.get_paragraphs()
            page_records = docling_reader.get_page_records()
            fallback_used = getattr(docling_reader, "fallback_used", False)
        except Exception as ext_err:
            logger.warning("Docling extraction error (%s); trying fallback extractor.", ext_err)
            try:
                from pdf_reader import PdfReader

                fallback_reader = PdfReader(io.BytesIO(raw_bytes), filename=filename)
                fallback_reader.extract_text(doc_id=doc_id, sha12=sha12)
                paragraphs = fallback_reader.get_paragraphs()
                page_records = fallback_reader.get_page_records()
                fallback_used = True
            except Exception as fb_err:
                return IngestionResult(
                    success=False,
                    doc_id=doc_id,
                    filename=filename,
                    sha256=sha256,
                    num_pages=validated.num_pages,
                    num_chunks=0,
                    error=f"Text extraction failed: {fb_err}",
                )

        # 4. Conditional RapidOCR fallback for low-text pages
        _report("Checking page OCR status…")
        try:
            page_records, paragraphs = apply_conditional_ocr(
                pdf_bytes=raw_bytes,
                page_records=page_records,
                existing_chunks=paragraphs,
                doc_id=doc_id,
                sha12=sha12,
                filename=filename,
            )
        except Exception as ocr_err:
            logger.warning("OCR processing warning: %s", ocr_err)

        # 5. Visual element detection and VLM analysis
        evidence_elements: list[EvidenceElement] = []
        try:
            analyzer = VisualAnalyzer()
            regions = analyzer.detect_visual_regions(raw_bytes)
            if regions and vlm_provider is not None:
                caps = vlm_provider.get_capabilities()
                if caps.is_local and caps.supports_vision:
                    _report(f"Analyzing {min(len(regions), 6)} visual elements with local VLM…")
                    evidence_elements = analyzer.analyze_visual_elements(
                        pdf_bytes=raw_bytes,
                        doc_id=doc_id,
                        provider=vlm_provider,
                        max_regions=6,
                    )
        except Exception as vis_err:
            logger.warning("Visual analysis warning for %s: %s", filename, vis_err)

        # 6. Guard against 0 chunks (CONCERNS P1 audit)
        if not paragraphs and not evidence_elements:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.doc_store.upsert_document(
                Document(
                    doc_id=doc_id,
                    filename=filename,
                    sha256=sha256,
                    size_bytes=validated.size_bytes,
                    num_pages=validated.num_pages,
                    status="failed",
                    upload_time=now_iso,
                    num_chunks=0,
                )
            )
            return IngestionResult(
                success=False,
                doc_id=doc_id,
                filename=filename,
                sha256=sha256,
                num_pages=validated.num_pages,
                num_chunks=0,
                error="Document produced 0 usable text or visual chunks (empty or unscannable PDF).",
            )

        # 7. Atomic SQLite Persistence
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        doc_model = Document(
            doc_id=doc_id,
            filename=filename,
            sha256=sha256,
            size_bytes=validated.size_bytes,
            num_pages=validated.num_pages,
            status="indexed",
            upload_time=now_iso,
            num_chunks=len(paragraphs),
        )

        try:
            self.doc_store.upsert_document(doc_model)
            if evidence_elements:
                self.doc_store.record_evidence_elements(evidence_elements)
            self.doc_store.record_pages_batch(page_records)

            chunk_models = [Chunk.model_validate(p) for p in paragraphs]
            self.doc_store.record_chunks(chunk_models)
        except Exception as db_err:
            logger.error("SQLite write failed for %s: %s", doc_id, db_err)
            return IngestionResult(
                success=False,
                doc_id=doc_id,
                filename=filename,
                sha256=sha256,
                num_pages=validated.num_pages,
                num_chunks=0,
                error=f"Database persistence failure: {db_err}",
            )

        # 8. Indexing into LanceDB
        _report(f"Generating embeddings and building hybrid index ({len(paragraphs)} chunks)…")
        try:
            if self.embedding is None:
                self.embedding = LocalEmbedding()

            if self.retriever is None:
                self.retriever = HybridRetriever(embedding_fn=self.embedding._embed_one)

            embeddings = self.embedding.get_embeddings([p["content"] for p in paragraphs])
            self.retriever.index_chunks(paragraphs, embeddings=embeddings.tolist())

            # Index visual evidence elements so questions about figures/tables retrieve them
            if evidence_elements and hasattr(self.retriever, "index_evidence_elements"):
                self.retriever.index_evidence_elements(evidence_elements)
        except Exception as idx_err:
            logger.error("LanceDB vector indexing error for %s: %s", doc_id, idx_err)
            # Revert document status to partial/failed
            try:
                self.doc_store.upsert_document(
                    Document(
                        doc_id=doc_id,
                        filename=filename,
                        sha256=sha256,
                        size_bytes=validated.size_bytes,
                        num_pages=validated.num_pages,
                        status="failed",
                        upload_time=now_iso,
                        num_chunks=0,
                    )
                )
            except Exception:
                pass
            return IngestionResult(
                success=False,
                doc_id=doc_id,
                filename=filename,
                sha256=sha256,
                num_pages=validated.num_pages,
                num_chunks=0,
                error=f"Vector indexing error: {idx_err}",
            )

        # 9. Disk cache write
        try:
            c_dir = cache_dir_for(self.cache_dir, sha256)
            c_dir.mkdir(parents=True, exist_ok=True)
            with open(c_dir / "pages.json", "w", encoding="utf-8") as f:
                json.dump([p.model_dump() for p in page_records], f, indent=2)
            with open(c_dir / "chunks.json", "w", encoding="utf-8") as f:
                json.dump(paragraphs, f, indent=2)
            with open(c_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(doc_model.model_dump(), f, indent=2)
        except Exception as cache_err:
            logger.warning("Cache write warning: %s", cache_err)

        _report(f"Successfully indexed {filename} ({len(paragraphs)} chunks).")
        return IngestionResult(
            success=True,
            doc_id=doc_id,
            filename=filename,
            sha256=sha256,
            num_pages=validated.num_pages,
            num_chunks=len(paragraphs),
            fallback_used=fallback_used,
            upload_time=now_iso,
        )
