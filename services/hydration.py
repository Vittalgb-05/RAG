"""Hydration service to restore document records and retriever state on application launch."""

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
import logging
import sqlite3

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding

logger = logging.getLogger(__name__)

# Callback signature: (completed, total, human-readable label).
ProgressCallback = Callable[[int, int, str], None]


@dataclass
class HydrationReport:
    """Summary of startup hydration and repair operations."""

    restored: int = 0
    repaired: int = 0
    failed: int = 0
    tombstones_consumed: int = 0


def _report_progress(
    progress_callback: ProgressCallback | None,
    completed: int,
    total: int,
    label: str,
) -> None:
    """Invoke the optional progress reporter without letting UI/callback errors abort hydration."""
    if progress_callback is None:
        return
    try:
        progress_callback(completed, total, label)
    except Exception as progress_err:  # pragma: no cover - UI boundary
        logger.debug("Hydration progress reporter failed: %s", progress_err)


def _consume_deletion_tombstones(doc_store: DocStore, retriever: HybridRetriever | None = None) -> int:
    """Purge vectors for documents deleted while no retriever was available.

    Returns the count of tombstones successfully consumed. Failures keep the
    tombstone so the next startup retries instead of silently resurrecting
    deleted chunks.
    """
    try:
        tombstones = doc_store.list_deletion_tombstones()
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.warning("Could not read deletion tombstones: %s", err, exc_info=True)
        return 0

    if not tombstones:
        return 0

    owns_retriever = retriever is None
    consumed_count = 0
    remaining: list[str] = []
    try:
        if retriever is None:
            retriever = HybridRetriever()
        for doc_id in tombstones:
            try:
                retriever.delete_document(doc_id)
            except (OSError, RuntimeError, ValueError, TypeError) as err:
                logger.warning("Deferred vector purge failed for %s; will retry: %s", doc_id, err)
                remaining.append(doc_id)
                continue
            try:
                doc_store.clear_deletion_tombstone(doc_id)
                consumed_count += 1
            except (sqlite3.Error, OSError, ValueError) as err:
                logger.warning("Could not clear deletion tombstone for %s; will retry: %s", doc_id, err)
                remaining.append(doc_id)
        if remaining:
            logger.warning("Deferred vector cleanup incomplete for %d document(s).", len(remaining))
        else:
            logger.info("Purged deferred vectors for %d tombstoned document(s).", len(tombstones))
        return consumed_count
    except (OSError, RuntimeError, ValueError, TypeError) as err:
        logger.warning("Could not initialize retriever for deferred vector cleanup: %s", err)
        return consumed_count
    finally:
        if owns_retriever and retriever is not None:
            try:
                retriever.close()
            except Exception as close_err:  # pragma: no cover - best-effort teardown
                logger.debug("Failed to close temporary retriever after tombstone cleanup: %s", close_err)


def hydrate_startup_state(
    doc_store: DocStore,
    retriever: HybridRetriever | None = None,
    embedding: LocalEmbedding | None = None,
    progress_callback: ProgressCallback | None = None,
) -> HydrationReport:
    """Hydrate document records and retriever state on application launch.

    Ensures that documents indexed in previous sessions are immediately visible
    in the library and searchable in the retriever without requiring re-upload (CR-01).

    Only documents whose vectors are actually missing are re-embedded; a library
    whose vector index is fully valid performs no embedding work.
    Also repairs evidence vectors (B13).

    Args:
        doc_store: Persistent document store to read the catalog from.
        retriever: Optional HybridRetriever instance to verify/repair against.
        embedding: Optional LocalEmbedding instance for computing repair vectors.
        progress_callback: Optional callback receiving (completed, total, label).

    Returns:
        HydrationReport with counts of restored, repaired, failed documents, and consumed tombstones.
    """
    report = HydrationReport()

    try:
        report.tombstones_consumed = _consume_deletion_tombstones(doc_store, retriever=retriever)
    except Exception as err:
        logger.warning("Error consuming tombstones during hydration: %s", err)

    try:
        docs = doc_store.list_documents()
    except (sqlite3.Error, OSError, ValueError) as e:
        logger.warning("Could not query documents for hydration: %s", e, exc_info=True)
        return report

    failed_docs = [d for d in docs if d.status == "failed"]
    report.failed += len(failed_docs)

    indexed_docs = [d for d in docs if d.status == "indexed"]
    if not indexed_docs:
        return report

    if retriever is None:
        try:
            retriever = HybridRetriever()
        except Exception as ret_err:
            logger.error("Failed to initialize retriever for hydration: %s", ret_err)
            report.failed += len(indexed_docs)
            return report

    if embedding is None:
        try:
            embedding = LocalEmbedding()
            if hasattr(retriever, "embedding_fn") and retriever.embedding_fn is None:
                retriever.embedding_fn = embedding._embed_one
        except Exception as emb_err:
            logger.debug("Embedding init notice during hydration: %s", emb_err)

    repair_docs = []
    for doc in indexed_docs:
        try:
            if retriever.has_document(doc.doc_id):
                report.restored += 1
                continue
        except Exception as check_err:
            logger.warning(
                "Vector coverage check failed for %s: %s",
                doc.doc_id,
                check_err,
                exc_info=True,
            )
        repair_docs.append(doc)

    if not repair_docs:
        logger.info(
            "Vector index valid for all %d indexed document(s); no re-embedding needed.",
            len(indexed_docs),
        )
        return report

    total = len(repair_docs)
    logger.info("Repairing vectors for %d of %d indexed document(s).", total, len(indexed_docs))
    _report_progress(progress_callback, 0, total, f"Repairing vector index (0/{total})")

    for position, doc in enumerate(repair_docs, start=1):
        _report_progress(
            progress_callback,
            position - 1,
            total,
            f"Repairing {doc.filename} ({position}/{total})",
        )
        chunks = doc_store.get_chunks_for_doc(doc.doc_id)
        if not chunks:
            logger.warning("Indexed document %s has no stored chunks; marking failed.", doc.doc_id)
            report.failed += 1
        else:
            try:
                logger.info("Auto-repairing missing vector index for %s (%s)", doc.filename, doc.doc_id)
                if embedding is None:
                    embedding = LocalEmbedding()
                embs = embedding.get_embeddings([c.content for c in chunks])
                retriever.index_chunks([c.model_dump() for c in chunks], embeddings=embs.tolist())

                # Visual evidence repair (B13)
                evidence = doc_store.get_evidence_for_doc(doc.doc_id)
                if evidence:
                    retriever.index_evidence_elements(evidence, filename=doc.filename)

                if not retriever.has_document(doc.doc_id):
                    raise RuntimeError("repair write did not produce retrievable vectors")
                report.repaired += 1
            except Exception as repair_err:
                logger.error(
                    "Vector repair failed for %s: %s",
                    doc.doc_id,
                    repair_err,
                    exc_info=True,
                )
                report.failed += 1

        _report_progress(
            progress_callback,
            position,
            total,
            f"Repairing vector index ({position}/{total})",
        )

    return report
