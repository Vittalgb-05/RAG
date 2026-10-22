"""
Local sentence embeddings using sentence-transformers.
Output: L2-normalised float32 vectors of dimension 384,
compatible with cosine similarity search in VectorIndex.
"""

import logging
import os
from pathlib import Path
import warnings

# Default to the PyTorch backend without overriding an explicit operator choice.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from sentence_transformers import SentenceTransformer

from core.models import EvidenceSnippet, RetrievalResult
from retrieval.vector_index import VectorIndex

logger = logging.getLogger(__name__)

# Process-level model cache to avoid duplicate SentenceTransformer instances across sessions (P1 audit)
_MODEL_CACHE: dict[tuple[str, str], SentenceTransformer] = {}


def get_shared_sentence_transformer(model_name: str = "all-MiniLM-L6-v2", device: str = "cpu") -> SentenceTransformer:
    """Retrieve or lazily initialize a shared process-level SentenceTransformer model.

    Args:
        model_name: HuggingFace model identifier.
        device: Hardware device ('cpu' or 'cuda').

    Returns:
        Shared SentenceTransformer instance.
    """
    cache_key = (model_name, device)
    if cache_key not in _MODEL_CACHE:
        logger.info("Loading SentenceTransformer model %s on %s...", model_name, device)
        _MODEL_CACHE[cache_key] = SentenceTransformer(model_name, device=device)
        logger.info("SentenceTransformer model %s ready and cached in process memory.", model_name)
    return _MODEL_CACHE[cache_key]


def clear_shared_model_cache() -> None:
    """Clear process-level model cache (useful for testing and memory reclamation)."""
    _MODEL_CACHE.clear()


class LocalEmbedding:
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        distance_metric: str = "cosine",
        device: str = "cpu",
        db_uri: Path | str | None = None,
    ):
        """
        Initialise the embedding model and an empty vector index.

        Args:
            model_name:      SentenceTransformer model ID.
            distance_metric: Distance metric for the index ('cosine' or 'euclidean').
            device:          Hardware device ('cpu' or 'cuda'). Pinned to 'cpu' by default
                             to preserve 100% of GPU VRAM for local VLM inference.
            db_uri:          Optional persistent storage path for LanceDB.
        """
        self.model_name = model_name
        self.device = device
        self.model = get_shared_sentence_transformer(self.model_name, self.device)

        self.store = VectorIndex(distance_metric=distance_metric, embedding_fn=self._embed_one)

    def _embed_one(self, text: str) -> list[float]:
        """
        Embed a single string and return it as a plain Python list.
        Used internally by VectorIndex to embed query strings at search time.
        """
        return self.get_embeddings([text])[0].tolist()

    def get_embeddings(self, texts: list[str]):
        """
        Embed a batch of strings locally and return them L2-normalised.
        """
        # normalize_embeddings=True applies L2 normalization for cosine similarity
        return self.model.encode(texts, normalize_embeddings=True)

    def build_index(self, chunks: list) -> None:
        """
        Embed all chunks in one batch and store them in the vector index.
        """
        if not chunks:
            return

        if isinstance(chunks[0], str):
            texts = chunks
            docs = [{"content": chunk} for chunk in chunks]
        else:
            texts = [chunk["content"] for chunk in chunks]
            docs = chunks

        embeddings = self.get_embeddings(texts)
        for doc, embedding in zip(docs, embeddings, strict=True):
            self.store.add_vector(embedding.tolist(), doc)
        logger.info("Indexed %d chunks.", len(chunks))

    def search(self, question: str, k: int = 3) -> list[tuple[dict, float]]:
        """
        Find the k chunks most semantically similar to the question.
        """
        return self.store.search(question, k=k)

    def search_hybrid(
        self,
        question: str,
        k: int = 5,
        doc_id: str | list[str] | None = None,
    ) -> RetrievalResult:
        """Execute dense search returning canonical RetrievalResult container (RETR-03, RETR-04)."""
        warnings.warn(
            "LocalEmbedding.search_hybrid() is deprecated; use HybridRetriever.search_hybrid() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        pool = k * 3 if doc_id else k
        results = self.search(question, k=pool)
        if doc_id:
            allowed = {doc_id} if isinstance(doc_id, str) else set(doc_id)
            results = [(d, s) for d, s in results if d.get("doc_id") in allowed][:k]

        snippets = []
        for rank, (doc, score) in enumerate(results, start=1):
            snippets.append(
                EvidenceSnippet(
                    content=doc.get("content", ""),
                    doc_id=doc.get("doc_id", "doc_default"),
                    filename=doc.get("filename", ""),
                    page=int(doc.get("page", 1)),
                    chunk_id=doc.get("chunk_id", f"c_{rank}"),
                    score=float(score),
                    rank=rank,
                )
            )
        return RetrievalResult(
            query=question,
            snippets=snippets,
            total_candidates=len(snippets),
            search_mode="dense",
        )

    def get_context(self, question: str, k: int = 3) -> str:
        """
        Retrieve the most relevant chunks for a question as a single string.
        """
        results = self.search(question, k=k)
        return "\n\n---\n\n".join(doc["content"] for doc, _ in results)
