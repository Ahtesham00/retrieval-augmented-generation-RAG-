# RAG Chat

A production-grade Retrieval-Augmented Generation (RAG) system that lets you upload documents, organise them into folders, and have multi-turn conversations grounded entirely in your own content. Every answer is traceable to a source chunk; the system never generates from general knowledge alone.

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Architecture overview](#architecture-overview)
3. [Technology choices](#technology-choices)
4. [Ingestion pipeline](#ingestion-pipeline)
5. [Retrieval pipeline](#retrieval-pipeline)
6. [Generation pipeline](#generation-pipeline)
7. [Caching strategy](#caching-strategy)
8. [Auth and security](#auth-and-security)
9. [Frontend](#frontend)
10. [Project structure](#project-structure)
11. [Getting started](#getting-started)
12. [Configuration reference](#configuration-reference)
13. [API reference](#api-reference)

---

## What it does

You create a **folder**, upload files into it (PDFs, Word docs, Markdown, code, images, JSON), and then open a chat window to ask questions. The system retrieves the most relevant chunks from your documents and feeds them as context to a language model, which streams a response back token by token. Citations are shown so you always know which file and section the answer came from.

Key capabilities:

- **Multi-format ingestion** — PDF, DOCX, Markdown, plain text, code files, JSON, images (OCR + vision caption)
- **Hierarchical chunking** — large documents are split at two levels so the retriever can auto-merge sibling chunks back into their parent for richer context
- **Hybrid retrieval** — dense vector search (Pinecone) combined with BM25 keyword search, fused via Reciprocal Rank Fusion
- **LLM reranking with fallback** — a second LLM pass scores retrieved chunks; if it returns nothing the system falls back to the top-k by original score
- **Streaming responses** — tokens are pushed via Server-Sent Events so the user sees output immediately
- **Multi-turn memory** — conversation history is loaded from MongoDB into a `ChatMemoryBuffer` so follow-up questions have full context
- **Query expansion control** — UI toggle lets users trade latency for recall by generating 1–4 query variants before retrieval
- **Per-conversation latency display** — wall-clock time visible on hover for every response

---

## Architecture overview

```
Browser (React + Vite)
    │  SSE stream / REST / WebSocket
    ▼
FastAPI (uvicorn)
    ├── Auth router        JWT issue / refresh
    ├── Folders router     CRUD
    ├── Files router       upload → background ingestion, WS status feed
    ├── Conversations router
    └── Chat router        POST → StreamingResponse (SSE)
            │
            ├── Ingestion service  (background task)
            │       text extraction → parse → enrich → embed
            │       → MongoDocumentStore (all nodes)
            │       → Pinecone (leaf vectors)
            │
            └── Generation service  (per request)
                    load history → build retriever → LLMRerank
                    → ContextChatEngine.astream_chat()
                    → stream tokens → persist messages
```

**Three storage layers, each serving a different purpose:**

| Store | What lives here | Why |
|---|---|---|
| **MongoDB** | Users, folders, files, conversations, messages, all parsed nodes with full metadata | Relational data + document store; Motor async driver fits the FastAPI event loop |
| **Pinecone** | Dense vector embeddings of leaf chunks | Purpose-built ANN index; namespace-per-folder gives logical isolation without multiple indexes |
| **Redis** | BM25 node lists, embedding cache, folder metadata | In-memory speed for hot data that would otherwise require a full DB scan on every query |

---

## Technology choices

### FastAPI + uvicorn
FastAPI's async-first design matches the IO-heavy nature of the pipeline: every step (DB queries, OpenAI calls, Pinecone queries) is awaited without blocking the event loop. Pydantic v2 models give free request/response validation. `StreamingResponse` with `text/event-stream` is a first-class citizen.

### LlamaIndex
Provides battle-tested implementations of the hard parts: `HierarchicalNodeParser`, `QueryFusionRetriever`, `AutoMergingRetriever`, `LLMRerank`, `ContextChatEngine`, `ChatMemoryBuffer`. Using these primitives avoids reinventing well-studied retrieval patterns and lets us focus on the system-level decisions.

### OpenAI (`text-embedding-3-small`, `gpt-4o-mini`, `gpt-4o`)
`text-embedding-3-small` at 1536 dimensions is the best cost/quality trade-off for document retrieval. `gpt-4o-mini` handles reranking, metadata extraction, and most chat queries. `gpt-4o` is reserved for queries exceeding 30 words where the extra context window and reasoning quality justify the cost.

### MongoDB (Motor async)
Chosen over a relational DB because the document shapes — especially nodes with arbitrary LlamaIndex metadata — are heterogeneous. Motor's async API is a natural fit for FastAPI. `MongoDocumentStore` from LlamaIndex uses MongoDB as its node backend, which keeps all node data in one place and avoids a separate vector-only store for metadata.

### Pinecone
Dense retrieval requires an Approximate Nearest Neighbour (ANN) index that can handle millions of vectors efficiently. Pinecone is managed, so there is no infrastructure to run. Namespaces per folder provide isolation without separate indexes.

### Redis
Three distinct caching uses (see [Caching strategy](#caching-strategy)). The BM25 cache is the most critical: building a BM25 index from a full docstore scan on every query is 200–500 ms of avoidable work; caching the serialised node list drops that to a single Redis GET.

---

## Ingestion pipeline

**Entry point:** `POST /folders/{id}/files` accepts uploads and queues each file as a FastAPI `BackgroundTask`.

### Phase 1 — Text extraction

Format routing:

| Format | Extractor | Fallback |
|---|---|---|
| PDF | `pypdf` page-by-page text extraction | pytesseract OCR |
| DOCX | `python-docx` paragraph walker | — |
| Markdown | Raw `Path.read_text` | — |
| Plain text / RST / log | Raw `Path.read_text` | — |
| Code (`.py`, `.ts`, `.go`, …) | Raw `Path.read_text` | — |
| JSON | Raw `Path.read_text` | — |
| Image | pytesseract OCR | OpenAI vision caption (`gpt-4o-mini`) |

Images use OCR first because it is free and fast. If OCR returns nothing (scanned image with no selectable text, diagram, etc.), the system falls back to asking `gpt-4o-mini` to describe the image, creating a searchable caption.

### Phase 2 — Parsing strategy selection

The parser is chosen by file type and extracted text size:

```
JSON                 → JSONNodeParser
Code                 → CodeSplitter (tree-sitter, language-aware)
                       fallback: SentenceSplitter if language unsupported
Markdown < 4 KB      → MarkdownNodeParser (preserve heading structure)
Markdown 4–16 KB     → MarkdownNodeParser + SentenceSplitter
Markdown > 16 KB     → HierarchicalNodeParser [2048 / 512 chars]  ← two-level
Text/PDF/DOCX < 16KB → SentenceSplitter (chunk_size=512, overlap=50)
Text/PDF/DOCX > 16KB → HierarchicalNodeParser [2048 / 512 chars]  ← two-level
```

**Why hierarchical for large documents?**
`HierarchicalNodeParser` produces parent nodes (2048-char chunks) and child nodes (512-char chunks). During retrieval, `AutoMergingRetriever` detects when several sibling children for the same parent are all retrieved and promotes the parent instead, giving the LLM more continuous context without bloating every retrieval result.

**Critical implementation note:** `HierarchicalNodeParser` cannot be placed inside an `IngestionPipeline`. The pipeline's internal deduplication logic sees both the parent and child nodes as "derived from the same document" and collapses them to one. The correct pattern is:

```
hier_parser.get_nodes_from_documents([doc])   # produces all levels
get_leaf_nodes(all_nodes)                      # isolate leaves
leaf_pipeline.arun(nodes=leaf_nodes)           # extractors + embedding on leaves only
parent_nodes + embedded_leaves → docstore      # store everything
embedded_leaves → Pinecone                     # only leaves get vectors
```

### Phase 3 — Metadata enrichment (extractors)

Each leaf node passes through three LlamaIndex extractors in the pipeline:

- **`TitleExtractor`** — identifies the document or section title. Adds useful context to the embedding text.
- **`QuestionsAnsweredExtractor(questions=3)`** — generates 3 questions this chunk can answer. Dramatically improves retrieval for question-style queries because the embedding captures question-answer proximity, not just keyword overlap.
- **`SummaryExtractor`** — writes a one-sentence summary of the chunk. Helps the LLM during reranking.

These fields are prepended to the chunk text before embedding, so the vector represents the semantic intent of the chunk, not just its literal words. **They are stripped from Pinecone metadata before upsert** (Pinecone's 40 KB/vector metadata limit) but kept in full in MongoDB, where `AutoMergingRetriever` reads them at query time.

### Phase 4 — Quality filter

Nodes shorter than 50 characters are dropped. These are typically navigation artefacts, empty headings, or parser noise that add nothing to retrieval quality.

### Phase 5 & 6 — Storage

All nodes (parents + leaves) → `MongoDocumentStore` with full metadata.  
Leaf nodes only → Pinecone with metadata stripped to stay under 40 KB.

### Idempotency and deduplication

Before ingesting an uploaded file the system computes its SHA-256 hash and checks:

1. If a file with the same hash and status `ready` **and `chunk_count > 0`** already exists → return the existing record immediately. The `chunk_count > 0` check matters: without it, a previously failed ingestion that left a stale `ready` record with 0 chunks would block re-ingestion silently.
2. If a file with the same hash exists in any other state → delete its chunks/vectors and re-ingest.
3. If a file with the same name but a different hash exists → delete the old file's data and ingest the new version.

### Real-time status via WebSocket

After upload the frontend connects to `WS /folders/{id}/files/status`. As the background ingestion progresses through states (`parsing` → `embedding` → `ready` / `failed`), it publishes JSON payloads into a per-folder `asyncio.Queue`. The WebSocket handler reads from the queue and pushes updates to the browser. A 30-second ping keeps the connection alive through proxies.

---

## Retrieval pipeline

**Entry point:** `build_retriever()` in `app/services/retrieval.py`, called per chat request.

### Step 1 — Dense retriever

`VectorStoreIndex.from_vector_store()` wraps the Pinecone namespace. `.as_retriever(similarity_top_k=20)` returns the 20 most semantically similar chunks to the embedded query.

### Step 2 — Sparse (BM25) retriever

`BM25Retriever` operates on in-memory `TextNode` objects. The node list is loaded from Redis (cache HIT) or scanned from `MongoDocumentStore` and then cached (cache MISS). This means BM25 retrieval costs ~1 ms on warm cache versus ~300 ms cold.

BM25 catches exact keyword matches that dense retrieval misses — product names, acronyms, version numbers, proper nouns.

### Step 3 — Reciprocal Rank Fusion

`QueryFusionRetriever` merges the dense and sparse result lists using Reciprocal Rank Fusion (RRF). Each document's fused score is `Σ 1 / (rank_i + 60)`. This is parameter-free, robust to score scale differences between dense and sparse, and consistently outperforms score-based merging in practice.

**Query expansion (`num_queries`):** the UI exposes a `1× / 2× / 4×` toggle. With `num_queries=1` (default), only the original query is used — fast, ~2–3 s end-to-end. With `num_queries > 1`, the LLM generates N-1 additional query variants before retrieval, each variant is embedded and queried separately, and all result lists are fused. This improves recall for ambiguous queries at the cost of 3–10 s per additional variant.

### Step 4 — Auto-merging

`AutoMergingRetriever` wraps the fusion retriever. After fusion it checks: for any set of sibling leaf nodes whose parent appears frequently enough among the top results (`simple_ratio_thresh=0.4` means ≥40% of a parent's children were retrieved), the siblings are replaced by their parent node. This gives the LLM a longer, more coherent passage instead of fragmented overlapping chunks.

### Step 5 — LLM reranking with fallback

`LLMRerank(top_n=5)` feeds the top retrieved nodes to `gpt-4o-mini` as (query, chunk) pairs and asks it to score relevance. The LLM has far more language understanding than a dot-product — it can recognise paraphrase, negation, and context.

**The fallback problem:** occasionally `LLMRerank` returns 0 nodes — it scores every chunk below its threshold. Without a fallback this produces an empty context and the system replies "no relevant content found." The `RerankWithFallback` wrapper detects this and returns the top-`TOP_K_FINAL` nodes sorted by their original retrieval score instead. This ensures the LLM always has something to work with for borderline queries.

```
retrieved nodes → LLMRerank → if len > 0: use reranked
                                if len == 0: sort by score, take top 5
```

---

## Generation pipeline

**Entry point:** `stream_chat()` in `app/services/generation.py`, called by the chat router.

### Conversation history

`MessageRepository.get_history()` loads prior messages from MongoDB and converts them to `ChatMessage` objects for LlamaIndex's `ChatMemoryBuffer`. This gives the `ContextChatEngine` full multi-turn awareness — follow-up questions like "expand on that" resolve correctly because the LLM sees what "that" referred to.

### Model selection

```python
if len(query.split()) > 30:
    model = "gpt-4o"          # complex, long queries
else:
    model = settings.CHAT_MODEL  # default: gpt-4o-mini
```

`gpt-4o-mini` handles the vast majority of queries faster and cheaper. `gpt-4o` is reserved for long, multi-part questions where extra reasoning depth matters.

### ContextChatEngine

`ContextChatEngine` wires together:
- the retriever (one retrieval pass, no double-fetching)
- the reranker as a `node_postprocessor`
- the `ChatMemoryBuffer` with loaded history
- the streaming LLM

`astream_chat()` retrieves context, builds the prompt (system + context + history + user query), and streams completion tokens. `source_nodes` on the response object contains the exact chunks used, which become citations.

### SSE streaming

Tokens are yielded as `data: {"type": "token", "content": "..."}` events. After the stream finishes, citations are sent as a single `data: {"type": "citations", "data": [...]}` event, then `data: {"type": "done"}`. The frontend consumes these via `fetch` + `ReadableStream` rather than `EventSource` — because `EventSource` cannot set custom headers and cannot send a Bearer token.

### Post-generation tasks

After the stream completes (user is already reading the response):
- The assistant message, citations, and retrieval trace (latency, chunk IDs, model) are persisted to MongoDB
- On the first turn, `gpt-4o-mini` generates a short conversation title and saves it

### Singleton embed model

`OpenAIEmbedding` is cached as a module-level singleton. Creating a new instance per request spawns a new `httpx` connection pool. The singleton reuses the same pool, eliminating the connection-setup overhead and the `TCPTransport closed` errors that appear when a short-lived pool is torn down mid-flight.

---

## Caching strategy

| Cache key | Content | TTL | Invalidated by |
|---|---|---|---|
| `emb:{sha256(model+text)}` | Embedding vector (pickle) | 30 days | Never (vectors are deterministic) |
| `bm25:{folder_id}` | List of leaf node dicts | 24 hours | File ingested or deleted |
| `folder:{folder_id}` | Folder document (JSON) | 1 hour | Folder updated |
| `qry:{sha256(folder+query+k+model)}` | Query result | 10 minutes | — (natural expiry) |

The embedding cache is the most impactful during ingestion — if the same text is ingested twice (same file re-uploaded), the embedding call is skipped entirely.

The BM25 cache is the most impactful at query time — without it every chat message triggers a full MongoDB collection scan to rebuild the in-memory BM25 index.

---

## Auth and security

JWT-based stateless auth with access + refresh tokens.

- **Registration:** `POST /auth/register` — password hashed with bcrypt (cost factor ~12).
- **Login:** `POST /auth/token` — returns `access_token` (30 min) + `refresh_token` (7 days).
- **Refresh:** `POST /auth/refresh` — exchanges a valid refresh token for a new access token.
- **Protected routes:** `Depends(get_current_user)` decodes and validates the Bearer token. Expired or tampered tokens raise HTTP 401.
- **Resource ownership:** every data-modifying endpoint verifies the resource belongs to the authenticated user. A user cannot read or modify another user's folders, files, or conversations.

Tokens are stored in `localStorage` on the frontend (Zustand `useAuthStore` with `persist`). The store is cleared on logout and on 401 responses.

---

## Frontend

React 18 + TypeScript + Tailwind CSS + Vite.

**State management:**
- `useAuthStore` (Zustand) — auth token and email, persisted to `localStorage`
- TanStack Query — all server state (folders, conversations, messages). `refetchOnWindowFocus: false` prevents the cascade of redundant GETs that would otherwise fire on every tab focus.

**Key UX decisions:**
- `staleTime: 30s` on all queries — data is considered fresh for 30 seconds. Explicit `invalidateQueries` after mutations ensures consistency without polling.
- Optimistic user messages — the user's message appears instantly in the chat window before the server acknowledges it. If the request fails, the optimistic entry is removed.
- `clearStreaming()` is called **before** `invalidateQueries` — this prevents the double-response flash where the streaming overlay and the newly fetched persisted message were briefly visible at the same time.
- WebSocket for file status — after upload, the frontend subscribes to real-time ingestion progress rather than polling the REST endpoint.

**Latency display:**
- Streaming responses show wall-clock elapsed time (client-side timer from request sent to `done` event).
- Persisted messages show `retrieval_trace.latency_ms` from the backend (time from retrieval start to stream start).

---

## Project structure

```
rag/
├── dev.sh                  # one-command dev setup and start
├── main.py                 # FastAPI app, startup hooks, router registration
├── requirements.in         # direct dependencies (no version pins) — edit this
├── requirements.txt        # pinned lockfile generated by pip-compile — do not edit
├── .env.example            # copy to .env and fill in keys
│
├── app/
│   ├── config.py           # pydantic-settings; lru_cache singleton
│   ├── database.py         # Motor async client, index creation on startup
│   ├── cache.py            # Redis singleton, all cache helpers
│   ├── pinecone_client.py  # Pinecone client + index singleton
│   │
│   ├── models/             # Pydantic v2 request/response models
│   │   ├── user.py
│   │   ├── folder.py
│   │   ├── file.py         # FileStatus enum, FileOut
│   │   ├── conversation.py
│   │   └── message.py      # Citation, RetrievalTrace, MessageOut
│   │
│   ├── core/
│   │   ├── security.py     # bcrypt, JWT encode/decode
│   │   └── dependencies.py # FastAPI Depends: get_current_user, get_folder_for_user
│   │
│   ├── repositories/       # thin async MongoDB wrappers (one per collection)
│   │   ├── user_repository.py
│   │   ├── folder_repository.py
│   │   ├── file_repository.py
│   │   ├── conversation_repository.py
│   │   └── message_repository.py
│   │
│   ├── routers/
│   │   ├── auth.py         # /auth/register, /auth/token, /auth/refresh
│   │   ├── folders.py      # CRUD /folders
│   │   ├── files.py        # upload, list, delete, WS status feed
│   │   ├── conversations.py
│   │   ├── chat.py         # SSE streaming chat endpoint
│   │   └── health.py       # /health, /health/deep
│   │
│   └── services/
│       ├── ingestion.py    # 7-phase ingestion pipeline
│       ├── retrieval.py    # dense + BM25 + RRF + auto-merge + rerank
│       └── generation.py   # history load → engine → stream → persist
│
└── frontend/
    ├── src/
    │   ├── api/            # typed fetch wrappers (chat.ts, folders.ts, …)
    │   ├── components/     # Layout, Sidebar, ChatWindow, ChatInput, MessageItem, …
    │   ├── hooks/          # useStreamChat (SSE consumer)
    │   └── store/          # useAuthStore (Zustand)
    └── package.json
```

---

## Getting started

**Prerequisites:** Python 3.10+, Node 18+, a running MongoDB instance, a running Redis instance, OpenAI API key, Pinecone account.

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd rag

# 2. Copy and fill in environment variables
cp .env.example .env
# Edit .env — at minimum set:
#   OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX, JWT_SECRET

# 3. Start everything (installs deps, compiles requirements.txt, starts both servers)
./dev.sh
```

`dev.sh` will:
1. Verify Python 3.10+ and Node 18+ are present
2. Create a Python virtualenv and install `pip-tools`
3. Compile `requirements.in` → `requirements.txt` (only when `requirements.in` changes)
4. Sync Python packages with `pip-sync`
5. Run `npm install` in `frontend/` (only when `package-lock.json` changes)
6. Start uvicorn on `localhost:8000` and Vite on `localhost:5173`
7. Tail both log files to the terminal; `Ctrl+C` stops everything cleanly

Logs are written to `.logs/backend.log` and `.logs/frontend.log`.

**Adding a Python dependency:**

```bash
# 1. Add the package name to requirements.in (no version pin)
echo "some-package" >> requirements.in

# 2. Re-run dev.sh — it detects the change and recompiles + syncs
./dev.sh
```

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required. Used for embeddings, reranking, chat, and metadata extraction |
| `PINECONE_API_KEY` | — | Required |
| `PINECONE_INDEX` | `rag-prod` | Name of the Pinecone index (must exist and be configured for 1536 dims) |
| `PINECONE_CLOUD` | `aws` | Cloud provider for the index (`aws`, `gcp`, `azure`) |
| `PINECONE_REGION` | `us-east-1` | Region of the Pinecone index |
| `MONGODB_URI` | `mongodb://localhost:27017/ragdb` | Motor connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `JWT_SECRET` | — | Required. Long random string; changing it invalidates all existing tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model (`text-embedding-3-small` or `text-embedding-3-large`) |
| `EMBEDDING_DIMENSIONS` | `1536` | Must match the Pinecone index dimensions. Allowed: `1536`, `3072` |
| `CHAT_MODEL` | `gpt-4o-mini` | Default chat model; `gpt-4o` used automatically for long queries |
| `MAX_FILE_SIZE_MB` | `50` | Upload size limit per file |
| `UPLOAD_DIR` | `uploads` | Local path where uploaded files are stored |
| `MAX_FILES_PER_FOLDER` | `100` | Hard cap on files per folder |
| `MAX_FOLDERS_PER_USER` | `20` | Hard cap on folders per user |

---

## API reference

The full interactive API documentation is available at `http://localhost:8000/docs` when the backend is running.

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create a new user account |
| POST | `/auth/token` | Login — returns access + refresh tokens |
| POST | `/auth/refresh` | Exchange a refresh token for a new access token |

### Folders

| Method | Path | Description |
|---|---|---|
| GET | `/folders` | List all folders for the current user |
| POST | `/folders` | Create a folder |
| PATCH | `/folders/{id}` | Update folder name or settings |
| DELETE | `/folders/{id}` | Delete folder and all its files, chunks, and conversations |

### Files

| Method | Path | Description |
|---|---|---|
| GET | `/folders/{id}/files` | List files in a folder |
| POST | `/folders/{id}/files` | Upload one or more files (returns immediately; ingestion runs in background) |
| DELETE | `/files/{id}` | Delete a file and remove its chunks from all stores |
| WS | `/folders/{id}/files/status` | WebSocket — real-time ingestion status updates |

### Conversations

| Method | Path | Description |
|---|---|---|
| GET | `/folders/{id}/conversations` | List conversations for a folder |
| POST | `/folders/{id}/conversations` | Create a conversation |
| PATCH | `/conversations/{id}` | Update title |
| DELETE | `/conversations/{id}` | Delete conversation and messages |

### Chat

| Method | Path | Description |
|---|---|---|
| GET | `/conversations/{id}/messages` | Fetch message history |
| POST | `/conversations/{id}/messages` | Send a message — returns `text/event-stream` SSE response |

**SSE event types:**

```jsonc
{"type": "token",     "content": "..."}      // streamed token
{"type": "citations", "data": [{...}]}        // after stream ends
{"type": "done"}                              // stream complete
{"type": "error",     "content": "..."}       // on failure
```

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Basic liveness check |
| GET | `/health/deep` | Checks MongoDB, Redis, and Pinecone connectivity |
