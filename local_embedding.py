"""
Local sentence embeddings using sentence-transformers.
Output: L2-normalised float32 vectors of dimension 384,
compatible with cosine similarity search in VectorIndex.
"""

from sentence_transformers import SentenceTransformer
from vector_index import VectorIndex


class LocalEmbedding:

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", distance_metric: str = "cosine"):
        """
        Initialise the embedding model and an empty vector index.

        Args:
            model_name:      SentenceTransformer model ID.
            distance_metric: Distance metric for the index ('cosine' or 'euclidean').
        """
        self.model_name = model_name
        print(f"[LocalEmbedding] Loading {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        print("[LocalEmbedding] Model ready.")

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
        for doc, embedding in zip(docs, embeddings):
            self.store.add_vector(embedding.tolist(), doc)
        print(f"[LocalEmbedding] Indexed {len(chunks)} chunks.")

    def search(self, question: str, k: int = 3) -> list[tuple[dict, float]]:
        """
        Find the k chunks most semantically similar to the question.
        """
        return self.store.search(question, k=k)

    def get_context(self, question: str, k: int = 3) -> str:
        """
        Retrieve the most relevant chunks for a question as a single string.
        """
        results = self.search(question, k=k)
        return "\n\n---\n\n".join(doc["content"] for doc, _ in results)