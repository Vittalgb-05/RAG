"""
SQLite document metadata store with WAL mode and schema versioning.

Persists document metadata, per-page extraction records, and chunk metadata across
application restarts. Uses per-operation connection lifecycles to ensure compatibility
with Windows file locks and Streamlit execution loops.
"""

from collections.abc import Generator
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any
from core.models import BBox, Chunk, Document, EvidenceElement, Page, SummaryResult

SCHEMA_V1_DDL = [
    """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,
        size_bytes INTEGER NOT NULL,
        num_pages INTEGER NOT NULL,
        status TEXT NOT NULL,
        upload_time TEXT NOT NULL,
        num_chunks INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
        doc_id TEXT NOT NULL,
        page_num INTEGER NOT NULL,
        status TEXT NOT NULL,
        char_count INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        num_chunks INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (doc_id, page_num)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        page INTEGER NOT NULL,
        content TEXT NOT NULL,
        char_start INTEGER,
        char_end INTEGER,
        bbox_json TEXT NULL,
        extraction TEXT NOT NULL DEFAULT 'pypdf',
        embedding_model TEXT NULL
    );
    """,
]

SCHEMA_V2_DDL = [
    """
    CREATE TABLE IF NOT EXISTS evidence_elements (
        element_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        page INTEGER NOT NULL,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        bbox_json TEXT NULL,
        source TEXT NOT NULL,
        model_version TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
    );
    """,
]

SCHEMA_V3_DDL = [
    """
    CREATE TABLE IF NOT EXISTS document_summaries (
        summary_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        profile TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        page_references_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        model_version TEXT NOT NULL DEFAULT '',
        UNIQUE(sha256, profile),
        FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_summaries_sha256 ON document_summaries(sha256);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_summaries_doc_id ON document_summaries(doc_id);
    """,
]

SCHEMA_V4_DDL = [
    """
    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id);
    """,
]

MIGRATIONS: dict[int, list[str]] = {
    1: SCHEMA_V1_DDL,
    2: SCHEMA_V2_DDL,
    3: SCHEMA_V3_DDL,
    4: SCHEMA_V4_DDL,
}


class DocStore:
    """
    ACID document and metadata store backed by standard library sqlite3.
    """

    def __init__(self, db_path: str | Path):
        """
        Initialize DocStore with a database file path.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize schema and verify user_version
        with self._connect() as conn:
            self._apply_migrations(conn)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Create a per-operation connection with WAL mode and busy timeouts,
        guaranteeing connection closing upon context exit.

        Yields:
            sqlite3.Connection: Configured SQLite connection.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        """
        Apply pending DDL schema migrations based on PRAGMA user_version.
        """
        cursor = conn.execute("PRAGMA user_version;")
        current_version = cursor.fetchone()[0]

        for version, statements in sorted(MIGRATIONS.items()):
            if current_version < version:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {version};")
                conn.commit()
                print(f"[DocStore] Applied migration v{version} to {self.db_path.name}")

    def upsert_document(self, doc: Document) -> None:
        """
        Insert or update a document record.

        Args:
            doc: Canonical Document instance.
        """
        if not isinstance(doc, Document):
            raise TypeError(f"Expected Document instance, got {type(doc).__name__}")

        query = """
        INSERT INTO documents (doc_id, filename, sha256, size_bytes, num_pages, status, upload_time, num_chunks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            filename = excluded.filename,
            size_bytes = excluded.size_bytes,
            num_pages = excluded.num_pages,
            status = excluded.status,
            upload_time = excluded.upload_time,
            num_chunks = excluded.num_chunks;
        """
        with self._connect() as conn:
            conn.execute(
                query,
                (
                    doc.doc_id,
                    doc.filename,
                    doc.sha256,
                    doc.size_bytes,
                    doc.num_pages,
                    doc.status,
                    doc.upload_time,
                    doc.num_chunks,
                ),
            )
            conn.commit()

    def get_document(self, doc_id: str) -> Document | None:
        """
        Retrieve a document by its doc_id.

        Args:
            doc_id: Unique document identifier (e.g. doc_<sha16>).

        Returns:
            Document | None: Canonical Document model or None if not found.
        """
        if not isinstance(doc_id, str):
            raise TypeError("doc_id must be a string")

        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM documents WHERE doc_id = ?;", (doc_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return Document.model_validate(dict(row))

    def get_by_sha(self, sha256: str) -> Document | None:
        """
        Retrieve a document by its SHA-256 digest for deduplication.

        Args:
            sha256: 64-character lowercase SHA-256 hex string.

        Returns:
            Document | None: Canonical Document model or None if not found.
        """
        if not isinstance(sha256, str):
            raise TypeError("sha256 must be a string")

        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM documents WHERE sha256 = ?;", (sha256,))
            row = cursor.fetchone()
            if row is None:
                return None
            return Document.model_validate(dict(row))

    def list_documents(self) -> list[Document]:
        """
        List all indexed documents ordered by upload time descending.

        Returns:
            list[Document]: List of canonical Document instances.
        """
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM documents ORDER BY upload_time DESC;")
            rows = cursor.fetchall()
            return [Document.model_validate(dict(row)) for row in rows]

    def record_pages_batch(self, pages: list[Page]) -> None:
        """
        Store a batch of page records in a single atomic transaction.

        Args:
            pages: List of canonical Page instances.
        """
        if not pages:
            return
        query = """
        INSERT INTO pages (doc_id, page_num, status, char_count, error, num_chunks)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id, page_num) DO UPDATE SET
            status = excluded.status,
            char_count = excluded.char_count,
            error = excluded.error,
            num_chunks = excluded.num_chunks;
        """
        params = []
        for p in pages:
            if not isinstance(p, Page):
                raise TypeError(f"Expected Page instance, got {type(p).__name__}")
            params.append(
                (
                    p.doc_id,
                    p.page_num,
                    p.status,
                    p.char_count,
                    p.error,
                    p.num_chunks,
                )
            )
        with self._connect() as conn:
            conn.executemany(query, params)
            conn.commit()

    def record_ingestion(
        self,
        doc: Document,
        pages: list[Page],
        chunks: list[Chunk],
        evidence: list[EvidenceElement] | None = None,
    ) -> None:
        """Atomically replace a document's pages, chunks, and evidence in one transaction.

        Ingestion previously committed the document row, pages, chunks, and evidence in
        separate transactions.  A failure part-way through left a document marked
        ``indexed`` with missing/duplicated child rows.  This method either commits all
        rows for the document or none of them, and removes stale child rows from a prior
        partial attempt so chunk counts stay truthful.

        Args:
            doc: Canonical Document instance (status and num_chunks are persisted as given).
            pages: Ordered page records for the document.
            chunks: Text chunks for the document.
            evidence: Optional visual evidence elements.

        Raises:
            TypeError: If an argument has the wrong canonical type.
        """
        if not isinstance(doc, Document):
            raise TypeError(f"Expected Document instance, got {type(doc).__name__}")

        evidence = evidence or []
        if not isinstance(pages, list) or any(not isinstance(p, Page) for p in pages):
            raise TypeError("pages must be a list of Page instances")
        if not isinstance(chunks, list) or any(not isinstance(c, Chunk) for c in chunks):
            raise TypeError("chunks must be a list of Chunk instances")
        if any(not isinstance(e, EvidenceElement) for e in evidence):
            raise TypeError("evidence must be a list of EvidenceElement instances")

        doc_params = (
            doc.doc_id,
            doc.filename,
            doc.sha256,
            doc.size_bytes,
            doc.num_pages,
            doc.status,
            doc.upload_time,
            doc.num_chunks,
        )
        page_params = [(p.doc_id, p.page_num, p.status, p.char_count, p.error, p.num_chunks) for p in pages]
        chunk_params = [
            (
                c.chunk_id,
                c.doc_id,
                c.filename,
                c.page,
                c.content,
                c.char_start,
                c.char_end,
                c.bbox.model_dump_json() if c.bbox else None,
                c.extraction,
                c.embedding_model,
            )
            for c in chunks
        ]
        evidence_params = [
            (
                e.element_id,
                e.doc_id,
                e.page,
                e.kind,
                e.content,
                e.bbox.model_dump_json() if e.bbox else None,
                e.source,
                e.model_version,
            )
            for e in evidence
        ]

        with self._connect() as conn:
            try:
                conn.execute("DELETE FROM chunks WHERE doc_id = ?;", (doc.doc_id,))
                conn.execute("DELETE FROM pages WHERE doc_id = ?;", (doc.doc_id,))
                conn.execute("DELETE FROM evidence_elements WHERE doc_id = ?;", (doc.doc_id,))

                conn.execute(
                    """
                    INSERT INTO documents (doc_id, filename, sha256, size_bytes, num_pages, status, upload_time, num_chunks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        filename = excluded.filename,
                        size_bytes = excluded.size_bytes,
                        num_pages = excluded.num_pages,
                        status = excluded.status,
                        upload_time = excluded.upload_time,
                        num_chunks = excluded.num_chunks;
                    """,
                    doc_params,
                )
                if page_params:
                    conn.executemany(
                        """
                        INSERT INTO pages (doc_id, page_num, status, char_count, error, num_chunks)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(doc_id, page_num) DO UPDATE SET
                            status = excluded.status,
                            char_count = excluded.char_count,
                            error = excluded.error,
                            num_chunks = excluded.num_chunks;
                        """,
                        page_params,
                    )
                if chunk_params:
                    conn.executemany(
                        """
                        INSERT INTO chunks (chunk_id, doc_id, filename, page, content, char_start, char_end, bbox_json, extraction, embedding_model)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            doc_id = excluded.doc_id,
                            filename = excluded.filename,
                            page = excluded.page,
                            content = excluded.content,
                            char_start = excluded.char_start,
                            char_end = excluded.char_end,
                            bbox_json = excluded.bbox_json,
                            extraction = excluded.extraction,
                            embedding_model = excluded.embedding_model;
                        """,
                        chunk_params,
                    )
                if evidence_params:
                    conn.executemany(
                        """
                        INSERT INTO evidence_elements (element_id, doc_id, page, kind, content, bbox_json, source, model_version)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(element_id) DO UPDATE SET
                            doc_id = excluded.doc_id,
                            page = excluded.page,
                            kind = excluded.kind,
                            content = excluded.content,
                            bbox_json = excluded.bbox_json,
                            source = excluded.source,
                            model_version = excluded.model_version;
                        """,
                        evidence_params,
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_page(self, page: Page) -> None:
        """
        Insert or update a page-level extraction record.

        Args:
            page: Canonical Page instance.
        """
        self.record_pages_batch([page])

    def get_pages_for_doc(self, doc_id: str) -> list[Page]:
        """Retrieve ordered page records for a document.

        Args:
            doc_id: Unique document identifier.

        Returns:
            list[Page]: Canonical Page instances ordered by page number.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM pages WHERE doc_id = ? ORDER BY page_num ASC;",
                (doc_id,),
            )
            return [Page.model_validate(dict(row)) for row in cursor.fetchall()]

    def record_chunks(self, chunks: list[Chunk]) -> None:
        """
        Store a batch of chunks in a single transaction.

        Args:
            chunks: List of canonical Chunk instances.
        """
        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list of Chunk instances")
        if not chunks:
            return

        query = """
        INSERT INTO chunks (chunk_id, doc_id, filename, page, content, char_start, char_end, bbox_json, extraction, embedding_model)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            doc_id = excluded.doc_id,
            filename = excluded.filename,
            page = excluded.page,
            content = excluded.content,
            char_start = excluded.char_start,
            char_end = excluded.char_end,
            bbox_json = excluded.bbox_json,
            extraction = excluded.extraction,
            embedding_model = excluded.embedding_model;
        """
        params = []
        for c in chunks:
            if not isinstance(c, Chunk):
                raise TypeError(f"Expected Chunk instance, got {type(c).__name__}")
            bbox_json = c.bbox.model_dump_json() if c.bbox else None
            params.append(
                (
                    c.chunk_id,
                    c.doc_id,
                    c.filename,
                    c.page,
                    c.content,
                    c.char_start,
                    c.char_end,
                    bbox_json,
                    c.extraction,
                    c.embedding_model,
                )
            )

        with self._connect() as conn:
            conn.executemany(query, params)
            conn.commit()

    def get_chunks_for_doc(self, doc_id: str) -> list[Chunk]:
        """
        Retrieve all stored chunks for a specific document.

        Args:
            doc_id: Unique document identifier.

        Returns:
            list[Chunk]: List of canonical Chunk instances.
        """
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM chunks WHERE doc_id = ? ORDER BY page ASC, rowid ASC;", (doc_id,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                row_dict: dict[str, Any] = dict(row)
                bbox_json = row_dict.pop("bbox_json", None)
                if bbox_json:
                    row_dict["bbox"] = BBox.model_validate_json(bbox_json)
                else:
                    row_dict["bbox"] = None
                results.append(Chunk.model_validate(row_dict))
            return results

    def record_evidence_elements(self, elements: list[EvidenceElement]) -> None:
        """
        Insert or update multimodal evidence elements (tables, charts, images).

        Args:
            elements: List of canonical EvidenceElement instances.
        """
        if not isinstance(elements, list):
            raise TypeError("elements must be a list of EvidenceElement instances")
        if not elements:
            return

        query = """
        INSERT INTO evidence_elements (element_id, doc_id, page, kind, content, bbox_json, source, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(element_id) DO UPDATE SET
            doc_id = excluded.doc_id,
            page = excluded.page,
            kind = excluded.kind,
            content = excluded.content,
            bbox_json = excluded.bbox_json,
            source = excluded.source,
            model_version = excluded.model_version;
        """
        params = []
        for e in elements:
            if not isinstance(e, EvidenceElement):
                raise TypeError(f"Expected EvidenceElement instance, got {type(e).__name__}")
            bbox_json = e.bbox.model_dump_json() if e.bbox else None
            params.append(
                (
                    e.element_id,
                    e.doc_id,
                    e.page,
                    e.kind,
                    e.content,
                    bbox_json,
                    e.source,
                    e.model_version,
                )
            )

        with self._connect() as conn:
            conn.executemany(query, params)
            conn.commit()

    def get_evidence_for_doc(self, doc_id: str) -> list[EvidenceElement]:
        """
        Retrieve all stored evidence elements for a specific document.

        Args:
            doc_id: Unique document identifier.

        Returns:
            list[EvidenceElement]: List of canonical EvidenceElement instances.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM evidence_elements WHERE doc_id = ? ORDER BY page ASC, rowid ASC;",
                (doc_id,),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                row_dict: dict[str, Any] = dict(row)
                bbox_json = row_dict.pop("bbox_json", None)
                if bbox_json:
                    row_dict["bbox"] = BBox.model_validate_json(bbox_json)
                else:
                    row_dict["bbox"] = None
                results.append(EvidenceElement.model_validate(row_dict))
            return results

    def save_summary(self, summary: SummaryResult) -> None:
        """
        Insert or update a synthesized document summary in SQLite.

        Args:
            summary: Canonical SummaryResult instance.
        """
        if not isinstance(summary, SummaryResult):
            raise TypeError(f"Expected SummaryResult instance, got {type(summary).__name__}")

        page_refs_json = json.dumps(summary.page_references)
        query = """
        INSERT INTO document_summaries (
            summary_id, doc_id, sha256, profile, summary_text, page_references_json, created_at, model_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sha256, profile) DO UPDATE SET
            summary_id = excluded.summary_id,
            doc_id = excluded.doc_id,
            summary_text = excluded.summary_text,
            page_references_json = excluded.page_references_json,
            created_at = excluded.created_at,
            model_version = excluded.model_version;
        """
        with self._connect() as conn:
            conn.execute(
                query,
                (
                    summary.summary_id,
                    summary.doc_id,
                    summary.sha256,
                    summary.profile,
                    summary.summary_text,
                    page_refs_json,
                    summary.created_at,
                    summary.model_version,
                ),
            )
            conn.commit()

    def get_summary(
        self,
        sha256: str,
        profile: str,
        model_version: str | None = None,
    ) -> SummaryResult | None:
        """
        Retrieve a summary by document SHA-256 and profile type.

        Args:
            sha256: 64-character lowercase SHA-256 hex string.
            profile: Summary profile name ('overview', 'detailed', etc.).
            model_version: Optional model version to invalidate stale cached summaries.

        Returns:
            SummaryResult | None: Canonical SummaryResult with cached=True, or None if not found or version mismatch.
        """
        if not isinstance(sha256, str) or not isinstance(profile, str):
            raise TypeError("sha256 and profile must be strings")

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM document_summaries WHERE sha256 = ? AND profile = ?;",
                (sha256, profile),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            row_dict = dict(row)
            if model_version is not None and row_dict.get("model_version") != model_version:
                # A missing/empty legacy version is stale too: serving it would bypass
                # invalidation after a model or chunking-config change.
                return None
            try:
                page_refs = json.loads(row_dict.get("page_references_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                page_refs = []
            return SummaryResult(
                summary_id=row_dict["summary_id"],
                doc_id=row_dict["doc_id"],
                sha256=row_dict["sha256"],
                profile=row_dict["profile"],
                summary_text=row_dict["summary_text"],
                page_references=page_refs,
                created_at=row_dict["created_at"],
                model_version=row_dict["model_version"],
                cached=True,
            )

    def list_summaries_for_doc(self, doc_id: str) -> list[SummaryResult]:
        """
        List all saved summaries for a specific document ID.

        Args:
            doc_id: Unique document identifier.

        Returns:
            list[SummaryResult]: List of summaries for the document.
        """
        if not isinstance(doc_id, str):
            raise TypeError("doc_id must be a string")

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM document_summaries WHERE doc_id = ? ORDER BY profile ASC;",
                (doc_id,),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                row_dict = dict(row)
                try:
                    page_refs = json.loads(row_dict.get("page_references_json") or "[]")
                except (json.JSONDecodeError, TypeError):
                    page_refs = []
                results.append(
                    SummaryResult(
                        summary_id=row_dict["summary_id"],
                        doc_id=row_dict["doc_id"],
                        sha256=row_dict["sha256"],
                        profile=row_dict["profile"],
                        summary_text=row_dict["summary_text"],
                        page_references=page_refs,
                        created_at=row_dict["created_at"],
                        model_version=row_dict["model_version"],
                        cached=True,
                    )
                )
            return results

    def delete_summaries_for_doc(self, doc_id: str) -> int:
        """
        Delete all summaries for a document.

        Args:
            doc_id: Unique document identifier.

        Returns:
            int: Number of deleted summary rows.
        """
        if not isinstance(doc_id, str):
            raise TypeError("doc_id must be a string")

        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM document_summaries WHERE doc_id = ?;", (doc_id,))
            conn.commit()
            return cursor.rowcount

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document and cascade delete associated pages, chunks, evidence elements, and summaries.

        Args:
            doc_id: Unique document identifier.

        Returns:
            bool: True if a document was deleted, False otherwise.
        """
        if not isinstance(doc_id, str):
            raise TypeError("doc_id must be a string")

        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE doc_id = ?;", (doc_id,))
            conn.execute("DELETE FROM pages WHERE doc_id = ?;", (doc_id,))
            conn.execute("DELETE FROM evidence_elements WHERE doc_id = ?;", (doc_id,))
            conn.execute("DELETE FROM document_summaries WHERE doc_id = ?;", (doc_id,))
            cursor = conn.execute("DELETE FROM documents WHERE doc_id = ?;", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0

    def purge_all(self) -> None:
        """
        Purge all document records, chunks, pages, evidence elements, and cached summaries from SQLite.
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks;")
            conn.execute("DELETE FROM pages;")
            conn.execute("DELETE FROM evidence_elements;")
            conn.execute("DELETE FROM document_summaries;")
            conn.execute("DELETE FROM documents;")
            conn.commit()
            conn.execute("VACUUM;")

    def count_documents(self) -> int:
        """Count total persisted documents in SQLite.

        Returns:
            Total integer count of document records.
        """
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM documents;")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def count_summaries(self) -> int:
        """Count total cached multi-profile summaries in SQLite.

        Returns:
            Total integer count of summary records.
        """
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM document_summaries;")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
