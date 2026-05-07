"""
Retrieval pipeline using LlamaIndex components.

Exposed to generation.py as build_retriever() which returns a fully assembled
BaseRetriever ready to plug into ContextChatEngine:

  QueryFusionRetriever (dense + BM25, RRF, num_queries=4 for query expansion)
  → AutoMergingRetriever (promotes parent nodes via MongoDocumentStore)

LLMRerank is returned separately as a postprocessor for ContextChatEngine.
"""
import asyncio
import logging
from typing import Any, Optional

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.retrievers import AutoMergingRetriever, QueryFusionRetriever
from llama_index.core.schema import NodeRelationship, NodeWithScore, QueryBundle, TextNode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.storage.docstore.mongodb import MongoDocumentStore
from llama_index.vector_stores.pinecone import PineconeVectorStore

from app.cache import get_bm25_nodes, set_bm25_nodes
from app.config import get_settings
from app.pinecone_client import get_index
from app.services.ingestion import _build_docstore

logger = logging.getLogger(__name__)

TOP_K_RETRIEVAL = 20
TOP_K_FINAL = 5


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_storage_context(namespace: str, docstore: MongoDocumentStore) -> StorageContext:
    vector_store = PineconeVectorStore(pinecone_index=get_index(), namespace=namespace)
    return StorageContext.from_defaults(vector_store=vector_store, docstore=docstore)


def _build_vector_retriever(storage_context: StorageContext, embed_model: OpenAIEmbedding) -> Any:
    index = VectorStoreIndex.from_vector_store(
        vector_store=storage_context.vector_store,
        embed_model=embed_model,
        storage_context=storage_context,
    )
    return index.as_retriever(similarity_top_k=TOP_K_RETRIEVAL)


def _load_bm25_from_docstore(docstore: MongoDocumentStore) -> list[dict] | None:
    """Synchronous — run via asyncio.to_thread. Returns serialisable node dicts."""
    all_nodes = list(docstore.docs.values())
    leaf_nodes = [
        n for n in all_nodes
        if isinstance(n, TextNode) and NodeRelationship.CHILD not in n.relationships
    ]
    if not leaf_nodes:
        return None
    return [
        {"id": n.node_id, "text": n.get_content(metadata_mode="none"), "metadata": n.metadata}
        for n in leaf_nodes
    ]


async def _build_bm25_retriever(folder_id: str, docstore: MongoDocumentStore) -> BM25Retriever | None:
    """
    Builds a BM25Retriever from leaf nodes.

    First checks Redis for a cached node list — avoids a full docstore scan on
    every query. Cache is invalidated by ingestion/deletion via invalidate_bm25_cache().
    """
    node_dicts = await get_bm25_nodes(folder_id)

    if node_dicts is None:
        logger.debug("[RETRIEVAL] BM25 cache MISS — loading from docstore  folder_id=%s", folder_id)
        node_dicts = await asyncio.to_thread(_load_bm25_from_docstore, docstore)
        if node_dicts is None:
            logger.warning("[RETRIEVAL] No leaf nodes for BM25  folder_id=%s", folder_id)
            return None
        await set_bm25_nodes(folder_id, node_dicts)
        logger.debug("[RETRIEVAL] BM25 cache SET  folder_id=%s  nodes=%d", folder_id, len(node_dicts))
    else:
        logger.debug("[RETRIEVAL] BM25 cache HIT  folder_id=%s  nodes=%d", folder_id, len(node_dicts))

    nodes = [
        TextNode(text=d["text"], id_=d["id"], metadata=d.get("metadata", {}))
        for d in node_dicts
    ]
    return BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=TOP_K_RETRIEVAL)


# ---------------------------------------------------------------------------
# Public API — used by generation.py
# ---------------------------------------------------------------------------

async def build_retriever(
    folder_id: str,
    namespace: str,
    embed_model: OpenAIEmbedding,
    llm: OpenAI,
    num_queries: int = 1,
) -> AutoMergingRetriever:
    """
    Assembles and returns a fully configured retriever:

      dense (Pinecone) + sparse (BM25 from docstore)
      → QueryFusionRetriever with RRF + num_queries=4 (LlamaIndex generates
        query variants internally — replaces manual query rewriting)
      → AutoMergingRetriever (reads parent nodes from MongoDocumentStore)

    The retriever is passed directly to ContextChatEngine so there is no
    separate retrieve() call — no double retrieval.
    """
    settings = get_settings()
    docstore = _build_docstore(folder_id, settings)
    storage_context = _build_storage_context(namespace, docstore)

    dense_retriever = _build_vector_retriever(storage_context, embed_model)
    bm25_retriever = await _build_bm25_retriever(folder_id, docstore)

    retrievers = [dense_retriever]
    if bm25_retriever:
        retrievers.append(bm25_retriever)

    # num_queries=1 (default): skip LLM query expansion for fast responses.
    # num_queries=2-4: LLM generates N-1 extra query variants and retrieves
    # with all of them, then fuses via RRF — improves recall at the cost of
    # 1-10s extra latency per additional variant.
    fusion_retriever = QueryFusionRetriever(
        retrievers=retrievers,
        llm=llm,
        similarity_top_k=TOP_K_FINAL,
        num_queries=num_queries,
        mode="reciprocal_rerank",
        use_async=True,
        verbose=False,
    )
    logger.debug("[RETRIEVAL] num_queries=%d  query_expansion=%s", num_queries, num_queries > 1)
    logger.debug("[RETRIEVAL] QueryFusionRetriever ready  sources=%s",
                 "dense + BM25" if bm25_retriever else "dense only")

    # AutoMergingRetriever wraps fusion_retriever — it is the single retriever
    # called by ContextChatEngine, so there is exactly one retrieval pass.
    auto_merging_retriever = AutoMergingRetriever(
        vector_retriever=fusion_retriever,
        storage_context=storage_context,
        simple_ratio_thresh=0.4,
        verbose=False,
    )
    return auto_merging_retriever


class RerankWithFallback(BaseNodePostprocessor):
    """
    Wraps LLMRerank and adds a fallback: if the reranker returns 0 nodes
    (LLM scored everything below threshold), return the top-k input nodes
    ordered by their original score instead of silently dropping all context.
    """

    reranker: LLMRerank
    top_n: int

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        reranked = self.reranker._postprocess_nodes(nodes, query_bundle)
        if reranked:
            return reranked
        logger.warning(
            "[RETRIEVAL] LLMRerank returned 0 nodes — falling back to top-%d by score", self.top_n
        )
        sorted_nodes = sorted(nodes, key=lambda n: n.score or 0.0, reverse=True)
        return sorted_nodes[: self.top_n]


def build_reranker(llm: OpenAI) -> RerankWithFallback:
    """
    LLMRerank wrapped with a fallback postprocessor.
    If the LLM scores all nodes below its threshold and returns 0 results,
    the fallback selects the top-TOP_K_FINAL nodes by original retrieval score.
    """
    reranker = LLMRerank(llm=llm, top_n=TOP_K_FINAL, choice_batch_size=10)
    return RerankWithFallback(reranker=reranker, top_n=TOP_K_FINAL)
