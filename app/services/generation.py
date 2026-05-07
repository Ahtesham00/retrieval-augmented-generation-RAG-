"""
Generation pipeline using LlamaIndex ContextChatEngine with SSE streaming.

Flow per chat turn:
  build_retriever() + build_reranker()
  → ContextChatEngine.astream_chat()
      ├─ retrieves context (AutoMergingRetriever → LLMRerank)
      ├─ injects history via ChatMemoryBuffer
      └─ streams LLM response
  → response.source_nodes → citations (no [N] parsing)
  → persist user + assistant messages → yield SSE events
"""
import json
import logging
import time
from typing import AsyncGenerator

from llama_index.core.chat_engine import ContextChatEngine
from llama_index.core.llms import ChatMessage, MessageRole as LlamaMessageRole
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

from app.config import get_settings
from app.database import get_database
from app.repositories import ConversationRepository, MessageRepository
from app.services.retrieval import build_retriever, build_reranker

logger = logging.getLogger(__name__)

# Module-level singleton — embed config never changes between requests, reusing
# the same instance avoids creating a new httpx connection pool per query.
_embed_model: OpenAIEmbedding | None = None


def _get_embed_model(settings) -> OpenAIEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = OpenAIEmbedding(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY,
            dimensions=settings.EMBEDDING_DIMENSIONS if settings.EMBEDDING_DIMENSIONS != 1536 else None,
        )
    return _embed_model


SYSTEM_PROMPT = (
    "You are an assistant that answers questions based solely on the provided document context. "
    "If the context does not contain the answer, say so explicitly. "
    "Always mention which document or section your answer comes from."
)

COMPLEX_QUERY_WORD_THRESHOLD = 30


def _select_model(query: str) -> str:
    settings = get_settings()
    if len(query.split()) > COMPLEX_QUERY_WORD_THRESHOLD:
        return "gpt-4o"
    return settings.CHAT_MODEL


async def _generate_title(query: str, llm: OpenAI) -> str:
    response = await llm.acomplete(
        f"Generate a short title (5 words or fewer) for a conversation starting with: {query}"
    )
    return str(response).strip().strip('"')[:80]


def _to_chat_messages(history: list[dict]) -> list[ChatMessage]:
    role_map = {"user": LlamaMessageRole.USER, "assistant": LlamaMessageRole.ASSISTANT}
    return [
        ChatMessage(role=role_map.get(m["role"], LlamaMessageRole.USER), content=m["content"])
        for m in history
    ]


# ---------------------------------------------------------------------------
# Main SSE streaming entry point
# ---------------------------------------------------------------------------

async def stream_chat(
    conversation_id: str,
    user_query: str,
    folder_id: str,
    namespace: str,
    num_queries: int = 1,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    db = get_database()
    msg_repo = MessageRepository(db)
    conv_repo = ConversationRepository(db)

    logger.info("[GENERATION] conversation_id=%s  folder_id=%s  query=%r",
                conversation_id, folder_id, user_query[:120])

    # Load history from MongoDB → ChatMemoryBuffer for ContextChatEngine
    history_docs = await msg_repo.get_history(conversation_id)
    chat_history = _to_chat_messages(history_docs)
    logger.debug("[GENERATION] Loaded %d prior messages", len(history_docs))

    model = _select_model(user_query)
    logger.info("[GENERATION] Model=%s  query_words=%d", model, len(user_query.split()))

    llm = OpenAI(model=model, api_key=settings.OPENAI_API_KEY, temperature=0.1)
    embed_model = _get_embed_model(settings)

    # Build retriever pipeline (dense + BM25 → fusion → auto-merge)
    start_ms = int(time.time() * 1000)
    retriever = await build_retriever(folder_id, namespace, embed_model, llm, num_queries=num_queries)
    reranker = build_reranker(llm)

    engine = ContextChatEngine.from_defaults(
        retriever=retriever,
        node_postprocessors=[reranker],
        memory=ChatMemoryBuffer.from_defaults(chat_history=chat_history),
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
    )

    # Persist user message before streaming starts
    await msg_repo.create(conversation_id, role="user", content=user_query)

    logger.debug("[GENERATION] Starting ContextChatEngine stream  model=%s", model)
    try:
        # astream_chat:
        #   1. Retrieves context nodes (source_nodes populated here)
        #   2. Streams LLM response token by token
        response = await engine.astream_chat(user_query)
    except Exception as exc:
        logger.exception("[GENERATION] ContextChatEngine error  conversation_id=%s", conversation_id)
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        return

    latency_ms = int(time.time() * 1000) - start_ms
    logger.info("[GENERATION] Retrieval complete  nodes=%d  latency_ms=%d",
                len(response.source_nodes), latency_ms)

    # Guard: if the retriever returned no nodes there is nothing to answer from
    if not response.source_nodes:
        logger.warning("[GENERATION] Retriever returned 0 nodes — no context available  folder_id=%s", folder_id)
        yield f"data: {json.dumps({'type': 'error', 'content': 'No relevant content found in your documents for this query.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Stream tokens
    full_response = ""
    try:
        async for token in response.async_response_gen():
            if token:
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as exc:
        logger.exception("[GENERATION] Stream error  conversation_id=%s", conversation_id)
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        return

    logger.info("[GENERATION] Stream complete  chars=%d", len(full_response))

    # Citations from source_nodes — no [N] parsing needed, LlamaIndex gives us
    # the exact chunks that were retrieved and used as context.
    citations: list[dict] = []
    for nws in (response.source_nodes or []):
        node = nws.node
        meta = node.metadata or {}
        citations.append({
            "chunk_id": node.node_id,
            "file_name": meta.get("file_name", ""),
            "snippet": node.get_content()[:300],
            "score": round(nws.score or 0.0, 4),
        })
    logger.info("[GENERATION] Citations: %d  sources=%s",
                len(citations), [c["file_name"] for c in citations])

    yield f"data: {json.dumps({'type': 'citations', 'data': citations})}\n\n"

    # Persist assistant message with citations + trace
    retrieval_trace = {
        "retrieved_chunk_ids": [nws.node.node_id for nws in (response.source_nodes or [])],
        "latency_ms": latency_ms,
        "model": model,
    }
    await msg_repo.create(
        conversation_id,
        role="assistant",
        content=full_response,
        citations=citations,
        retrieval_trace=retrieval_trace,
    )
    await conv_repo.touch(conversation_id)

    # Auto-generate conversation title on first turn
    if not history_docs:
        title = await _generate_title(user_query, llm)
        await conv_repo.update_title(conversation_id, title)
        logger.info("[GENERATION] Auto-title: %r", title)

    logger.info("[GENERATION] ✓ Done  conversation_id=%s  model=%s  latency_ms=%d  citations=%d",
                conversation_id, model, latency_ms, len(citations))

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
