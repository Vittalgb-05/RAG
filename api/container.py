"""Application container holding singletons and background lifecycle tasks."""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import threading
from typing import TYPE_CHECKING

from core.doc_store import DocStore
from core.local_llm import AiModel
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding
from services.chat_turn import ChatTurnService
from services.ingestion import IngestionService
from services.lifecycle import LifecycleService
from services.hydration import hydrate_startup_state, HydrationReport
from api.jobs import JobManager
from api.cloud_state import CloudState

if TYPE_CHECKING:
    from api.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Process-wide singleton container."""

    settings: Settings
    doc_store: DocStore
    embedding: LocalEmbedding
    retriever: HybridRetriever
    ai_model: AiModel
    chat: ChatTurnService
    ingestion: IngestionService
    lifecycle: LifecycleService
    jobs: JobManager
    cloud: CloudState
    chat_lock: threading.Lock = field(default_factory=threading.Lock)
    ready: threading.Event = field(default_factory=threading.Event)
    hydration: HydrationReport | None = None

    @classmethod
    def build(cls, s: Settings) -> AppContainer:
        s.data_dir.mkdir(parents=True, exist_ok=True)
        s.log_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = s.data_dir / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        doc_store = DocStore(s.data_dir / "documents.db")
        embedding = LocalEmbedding()
        retriever = HybridRetriever(db_uri=str(s.data_dir / "lancedb"), embedding_fn=embedding._embed_one)
        ai_model = AiModel()
        cloud = CloudState(ai_model)
        jobs = JobManager()
        chat = ChatTurnService(ai_model.validate_response)
        ingestion = IngestionService(
            doc_store=doc_store,
            hybrid_retriever=retriever,
            local_embedding=embedding,
            cache_dir=cache_dir,
        )
        lifecycle = LifecycleService(
            doc_store=doc_store,
            retriever=retriever,
            embedding=embedding,
            cache_dir=cache_dir,
        )

        return cls(
            settings=s,
            doc_store=doc_store,
            embedding=embedding,
            retriever=retriever,
            ai_model=ai_model,
            chat=chat,
            ingestion=ingestion,
            lifecycle=lifecycle,
            jobs=jobs,
            cloud=cloud,
        )

    def start_background_hydration(self) -> None:
        """Launch startup state hydration in a background daemon thread."""

        def run() -> None:
            try:
                logger.info("Starting background state hydration...")
                self.hydration = hydrate_startup_state(
                    self.doc_store,
                    retriever=self.retriever,
                    embedding=self.embedding,
                )
                logger.info("Hydration completed: %s", self.hydration)
            except Exception as exc:
                logger.error("Hydration thread error: %s", exc, exc_info=True)
            finally:
                self.ready.set()

        threading.Thread(target=run, name="rag-hydrate", daemon=True).start()

    def shutdown(self) -> None:
        """Gracefully release resources."""
        logger.info("Shutting down container resources...")
        try:
            self.jobs.shutdown()
        except Exception as e:
            logger.debug("Error shutting down jobs: %s", e)
        try:
            self.ai_model.close()
        except Exception as e:
            logger.debug("Error closing AI model: %s", e)
        try:
            self.retriever.close()
        except Exception as e:
            logger.debug("Error closing retriever: %s", e)
        try:
            self.doc_store.close()
        except Exception as e:
            logger.debug("Error closing doc store: %s", e)
