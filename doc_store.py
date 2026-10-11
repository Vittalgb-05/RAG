"""
SQLite document metadata store with WAL mode and schema versioning.

Persists document metadata, per-page extraction records, and chunk metadata across
application restarts. Uses per-operation connection lifecycles to ensure compatibility
with Windows file locks and Streamlit execution loops.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any
from models import BBox, Chunk, Document, Page

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

MIGRATIONS: dict[int, list[str]] = {
    1: SCHEMA_V1_DDL,
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

    def record_page(self, page: Page) -> None:
        """
        Insert or update a page-level extraction record.

        Args:
            page: Canonical Page instance.
        """
        if not isinstance(page, Page):
            raise TypeError(f"Expected Page instance, got {type(page).__name__}")

        query = """
        INSERT INTO pages (doc_id, page_num, status, char_count, error, num_chunks)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id, page_num) DO UPDATE SET
            status = excluded.status,
            char_count = excluded.char_count,
            error = excluded.error,
            num_chunks = excluded.num_chunks;
        """
        with self._connect() as conn:
            conn.execute(
                query,
                (
                    page.doc_id,
                    page.page_num,
                    page.status,
                    page.char_count,
                    page.error,
                    page.num_chunks,
                ),
            )
            conn.commit()

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
