# GEMINI.md - KnowBot Project Mandates

## Core Identity
KnowBot is an **Agentic RAG (Retrieval-Augmented Generation)** system optimized for Vietnamese technical documentation. It prioritizes **faithfulness**, **source traceability**, and **hybrid search precision** to eliminate hallucinations in internal corporate environments.

---

## Architectural Mandates

### 1. The 7-Stage Query Pipeline
Every user query must traverse these stages in sequence:
1.  **Multi-Stage Cache:** 
    -   *Semantic Cache:* Qdrant-backed embedding lookup (threshold 0.90).
    -   *Rewrite Cache:* Skips LLM rewriting for repeat queries.
2.  **Query Analyzer:** Intent detection (`technical` vs `general`), `complexity_score`, and `ambiguity_score`.
3.  **Conditional Rewriter:** Triggers only if `complexity >= 0.5` or `ambiguity >= 0.4`. Includes an "over-rewrite guard" (output length < 2.5x original).
4.  **Hybrid Retrieval:** Reciprocal Rank Fusion (RRF) combining:
    -   *Dense:* `AITeamVN/Vietnamese_Embedding` (1024d).
    -   *Sparse:* BM25 via `fastembed`.
5.  **Adaptive Reranker:** Cohere `rerank-multilingual-v3.0`. Top-k is dynamically adjusted based on complexity (2 to 4 chunks).
6.  **Context Builder:** Deduplication and strict truncation (12,000 chars). Formats source as `[Nguồn: filename.md]`.
7.  **Generator:** Groq `LLaMA 3.3-70B`. Strict adherence to context; must admit if info is missing.

### 2. Ingestion & Chunking Logic
-   **Split Point:** Split on `##` sections only. Keep `###` subsections within their parent chunk to preserve semantic context.
-   **Enrichment:** Prepend the section title to every sub-chunk to ensure each is self-contained.
-   **Table Safety:** Use `smart_markdown_chunker` to prevent splitting inside Markdown tables.
-   **Metadata:** 2-tier extraction (Path-based first, content-regex scoring as fallback).

---

## Engineering Standards

### 1. Technical Stack
-   **Compute:** Python 3.11+, FastAPI (Backend), Streamlit (Frontend).
-   **Storage:** Qdrant (Vectors), MinIO (S3-compatible .md storage).
-   **Models:** LLaMA 3.3-70B (Groq), Cohere Rerank, Vietnamese_Embedding (Sentence-Transformers).
-   **Tracing:** Every pipeline component must use `@traceable` for LangSmith observability.

### 2. Performance & Resource Profiling
-   Use `ResourceProfile` to adjust token budgets and prompt tiers based on query complexity.
-   **Multi-topic Handling:** Queries with multiple "?" or high complexity are decomposed into sub-queries (max 3) with a shared document budget.

### 3. Verification & Evaluation
-   **EVAL_MODE:** When `EVAL_MODE=true`, semantic caches must be bypassed to ensure retrieval quality metrics are accurate.
-   **Metrics:** Target `Strict Faithfulness > 0.9` and `Answer Relevance > 0.9`.

---

## Security & Reliability Protocols
-   **No Hallucinations:** Never attempt to answer technical questions without document grounding.
-   **Citation Format:** Citations must be explicitly linked to the filename from MinIO.
-   **Data Privacy:** Internal TechCorp documents (HR/IT) are protected; the RAG system is the only authorized interface for LLM interaction with these files.

---

## Development Workflow
-   **Local Development:** Use Docker Compose for services. Hot-reload is enabled via bind mounts.
-   **Environment:** Maintain `.env` keys for Groq, Cohere, and LangSmith.
-   **Commits:** Focus messages on the "why" of pipeline adjustments.
