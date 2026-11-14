"""Ingestion service coordinating validation, extraction, OCR, visual analysis, and indexing."""

from __future__ import annotations
from dataclasses import dataclass
import datetime
import io
import logging
from pathlib import Path
from typing import Any
from collections.abc import Callable

from core.doc_store import DocStore
from ingestion.docling_reader import DoclingReader
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding
from core.models import Chunk, Document, EvidenceElement, Page
from ingestion.ocr_fallback import apply_conditional_ocr
from ingestion.upload_validation import validate_pdf_bytes
from ingestion.visual_analyzer import VisualAnalyzer

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
    already_indexed: bool = False
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
        progress_callback: Callable[..., None] | None = None,
    ) -> IngestionResult:
        """Process and index a PDF file into SQLite and LanceDB.

        Args:
            raw_bytes: Raw binary content of the PDF.
            filename: Original uploaded filename.
            vlm_provider: Optional local VLM provider for figure/table understanding.
            progress_callback: Optional progress reporter receiving (stage, pct) or (msg).

        Returns:
            IngestionResult with processing metadata and status.
        """

        def _report(stage: str, pct: int, msg: str | None = None) -> None:
            if progress_callback:
                try:
                    progress_callback(stage, pct)
                except TypeError:
                    progress_callback(msg or f"{stage} ({pct}%)")
            logger.info("[%s] [%s %d%%] %s", filename, stage, pct, msg or stage)

        # 1. Validation (5%)
        _report("validate", 5, f"Validating {filename}…")
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

        # 2. Deduplication check (10%)
        _report("dedupe", 10, f"Checking deduplication for {filename}…")
        existing_doc = self.doc_store.get_by_sha(sha256)
        if existing_doc and existing_doc.status == "indexed" and existing_doc.num_chunks > 0:
            has_vectors = self.retriever.has_document(existing_doc.doc_id) if self.retriever else True
            if has_vectors:
                _report("dedupe", 10, f"Document already indexed as {doc_id}.")
                return IngestionResult(
                    success=True,
                    doc_id=doc_id,
                    filename=existing_doc.filename or filename,
                    sha256=sha256,
                    num_pages=existing_doc.num_pages,
                    num_chunks=existing_doc.num_chunks,
                    already_indexed=True,
                    upload_time=existing_doc.upload_time,
                )
            else:
                # Missing vectors in LanceDB: attempt fast repair from persisted SQLite chunks
                persisted_chunks = self.doc_store.get_chunks_for_doc(existing_doc.doc_id)
                if persisted_chunks and self.retriever:
                    _report("dedupe", 10, f"Restoring vector index for {filename} from stored SQLite chunks…")
                    try:
                        if self.embedding is None:
                            self.embedding = LocalEmbedding()
                        embs = self.embedding.get_embeddings([c.content for c in persisted_chunks])
                        chunk_dicts = [c.model_dump() for c in persisted_chunks]
                        self.retriever.index_chunks(chunk_dicts, embeddings=embs.tolist())
                        if not self.retriever.has_document(existing_doc.doc_id):
                            raise RuntimeError("Repair wrote no retrievable vectors.")
                        return IngestionResult(
                            success=True,
                            doc_id=doc_id,
                            filename=existing_doc.filename or filename,
                            sha256=sha256,
                            num_pages=existing_doc.num_pages,
                            num_chunks=len(persisted_chunks),
                            already_indexed=True,
                            upload_time=existing_doc.upload_time,
                        )
                    except Exception as repair_err:
                        logger.warning(
                            "Vector repair notice for %s (%s); proceeding to full extraction.", doc_id, repair_err
                        )

        # 3. Extraction (40%)
        _report("extract", 40, "Extracting text and document structure…")
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
                from ingestion.pdf_reader import PdfReader

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

        # 4. Conditional OCR (55%)
        _report("ocr", 55, "Checking page OCR status…")
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

        # 5. Visual element detection and VLM analysis (70%)
        _report("visual", 70, "Detecting visual elements…")
        evidence_elements: list[EvidenceElement] = []
        try:
            analyzer = VisualAnalyzer()
            regions = analyzer.detect_visual_regions(raw_bytes)
            if regions and vlm_provider is not None:
                caps = vlm_provider.get_capabilities()
                if caps.is_local and caps.supports_vision:
                    _report("visual", 70, f"Analyzing {min(len(regions), 6)} visual elements with local VLM…")

                    def _vlm_prog(cur: int, tot: int, lbl: str) -> None:
                        _report("visual", 70, f"Visual element {cur}/{tot}: {lbl}")

                    evidence_elements = analyzer.analyze_visual_elements(
                        pdf_bytes=raw_bytes,
                        doc_id=doc_id,
                        provider=vlm_provider,
                        max_regions=6,
                        progress_callback=_vlm_prog,
                    )
        except Exception as vis_err:
            logger.warning("Visual analysis warning for %s: %s", filename, vis_err)

        # 6. Guard against 0 chunks (CONCERNS P1 audit)
        if not paragraphs and not evidence_elements:
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            self.doc_store.record_ingestion(
                Document(
                    doc_id=doc_id,
                    filename=filename,
                    sha256=sha256,
                    size_bytes=validated.size_bytes,
                    num_pages=validated.num_pages,
                    status="failed",
                    upload_time=now_iso,
                    num_chunks=0,
                ),
                pages=[],
                chunks=[],
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

        # 7. Persistence (80%) - B14: status="indexing" first!
        _report("persist", 80, "Persisting document structure to SQLite…")
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        doc_model = Document(
            doc_id=doc_id,
            filename=filename,
            sha256=sha256,
            size_bytes=validated.size_bytes,
            num_pages=validated.num_pages,
            status="indexing",  # B14: initially "indexing" until vectors verified
            upload_time=now_iso,
            num_chunks=len(paragraphs),
        )

        try:
            chunk_models = [Chunk.model_validate(p) for p in paragraphs]
            self.doc_store.record_ingestion(
                doc_model,
                pages=page_records,
                chunks=chunk_models,
                evidence=evidence_elements,
            )
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

        # 8. Embedding (92%) & Indexing (100%)
        _report("embed", 92, f"Generating embeddings ({len(paragraphs)} chunks)…")
        try:
            if self.embedding is None:
                self.embedding = LocalEmbedding()

            if self.retriever is None:
                self.retriever = HybridRetriever(embedding_fn=self.embedding._embed_one)

            # Drop any stale vectors left by a previous attempt
            self.retriever.delete_document(doc_id)

            embeddings = self.embedding.get_embeddings([p["content"] for p in paragraphs])

            _report("index", 100, "Writing vectors to LanceDB and verifying…")
            self.retriever.index_chunks(paragraphs, embeddings=embeddings.tolist())

            # Verify the write actually landed before declaring indexing successful (B14)
            if not self.retriever.has_document(doc_id):
                raise RuntimeError("Vector write completed but no chunks are retrievable for the document.")

            # Index visual evidence elements
            if evidence_elements and hasattr(self.retriever, "index_evidence_elements"):
                try:
                    self.retriever.index_evidence_elements(evidence_elements, filename=filename)
                except Exception as vis_idx_err:
                    logger.error("Visual evidence indexing failed for %s: %s", doc_id, vis_idx_err)

            # B14: Transition document status to "indexed" after verification
            self.doc_store.update_document_status(doc_id, "indexed")
        except Exception as idx_err:
            logger.error("LanceDB vector indexing error for %s: %s", doc_id, idx_err)
            try:
                self.doc_store.update_document_status(doc_id, "failed")
            except Exception as mark_err:
                logger.error("Failed to mark %s as failed after indexing error: %s", doc_id, mark_err)
            return IngestionResult(
                success=False,
                doc_id=doc_id,
                filename=filename,
                sha256=sha256,
                num_pages=validated.num_pages,
                num_chunks=0,
                error=f"Vector indexing error: {idx_err}",
            )

        _report("index", 100, f"Successfully indexed {filename} ({len(paragraphs)} chunks).")
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
