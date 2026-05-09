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
2.  **Query Analyzer:** Intent detection (`technical` vs `general`) với cơ chế **keyword-based override** để đảm bảo không bỏ sót các câu hỏi chính sách/quy trình. Tính toán `complexity_score` và `ambiguity_score`.
3.  **Conditional Rewriter:** Triggers only if `complexity >= 0.5` or `ambiguity >= 0.4`. Includes an "over-rewrite guard" (output length < 2.5x original).
4.  **Hybrid Retrieval:** Reciprocal Rank Fusion (RRF) combining:
    -   *Dense:* `AITeamVN/Vietnamese_Embedding` (1024d).
    -   *Sparse:* BM25 via `fastembed`.
5.  **Adaptive Reranker:** Cohere `rerank-multilingual-v3.0`. Top-k is dynamically adjusted based on complexity (2 to 4 chunks).
6.  **Context Builder:** Deduplication and strict truncation (12,000 chars). Formats source as `[Nguồn: filename.md]`.
7.  **Generator:** Groq `LLaMA 3.3-70B`. Sử dụng **API đồng bộ (Synchronous)** để đảm bảo độ tin cậy của việc theo dõi Token Usage trên LangSmith. BẮT BUỘC trình bày dữ liệu có tính chất liệt kê/thuộc tính dưới dạng **BẢNG Markdown chuẩn**. TUYỆT ĐỐI KHÔNG dùng thẻ HTML (`<div>`, `<table>`) trong output. Trả lời thẳng vào vấn đề, không mào đầu máy móc. Bắt buộc thừa nhận nếu thông tin kỹ thuật bị thiếu.

### 2. Ingestion & Chunking Logic
-   **Multi-format Parsing:** Use `LightweightDocumentParser` (pymupdf4llm, python-docx, python-pptx) to rapidly process PDF, DOCX, and PPTX files without heavy OCR models, preserving Markdown table structures for accurate chunking.
-   **Split Point:** Split on `##` sections only. Keep `###` subsections within their parent chunk to preserve semantic context.
-   **Enrichment:** Prepend the section title to every sub-chunk to ensure each is self-contained.
-   **Table Safety:** Use `smart_markdown_chunker` to prevent splitting inside Markdown tables.
-   **Metadata:** 2-tier extraction (Path-based first, content-regex scoring as fallback).

---

## Engineering Standards

### 1. Technical Stack
-   **Compute:** Python 3.11+, FastAPI (Backend), Streamlit (Frontend).
-   **Storage:** Qdrant (Vectors), MinIO (S3-compatible .md/pdf/docx/pptx storage).
-   **Models:** LLaMA 3.3-70B (Groq), Cohere Rerank, Vietnamese_Embedding (Sentence-Transformers).
-   **Parsing:** `pymupdf4llm` (PDF), `python-docx`, `python-pptx` (Lightweight Document Parser).
-   **Tracing:** Every pipeline component must use `@traceable` for LangSmith observability.

### 2. Performance & Resource Profiling
-   Use `ResourceProfile` to adjust token budgets and prompt tiers based on query complexity.
-   **Multi-topic Handling:** Queries with multiple "?" or high complexity are decomposed into sub-queries (max 3) with a shared document budget.

### 3. Verification & Evaluation
-   **EVAL_MODE:** When `EVAL_MODE=true`, semantic caches must be bypassed to ensure retrieval quality metrics are accurate.
-   **Metrics:** Target `Strict Faithfulness > 0.9` and `Answer Relevance > 0.9`.

---

## Security & Reliability Protocols

### 1. No Hallucinations
-   Never attempt to answer technical questions without document grounding.
-   **Citation Format:** Citations phải được liên kết rõ ràng với tên file từ MinIO. Hệ thống hỗ trợ **interactive preview** (modal) với khả năng tự động cuộn đến vị trí trích xuất (auto-scroll).

### 2. Security Guardrails
-   **Prompt Injection:** Use `_INJECTION_PATTERNS` to detect and block malicious system overrides before the pipeline starts.
-   **Off-topic Guard:** Nếu retrieval không trả về ngữ cảnh **trực tiếp và cụ thể** khớp với tình huống (Direct Match), hệ thống BẮT BUỘC phải từ chối trả lời thay vì suy diễn từ các dữ liệu chung chung.
-   **PII Scrubbing:** All generator outputs MUST pass through `pii_scrubber.py` to mask sensitive data (emails, phones, IDs) before reaching the user.

---

## Infrastructure & Security Protocols

### 1. Security & Access Control
-   **API Protection:** Sensitive endpoints (`/chat`, `/keys/status`) MUST be protected by `X-API-Key` authentication.
-   **Public Health:** The `/health` endpoint MUST remain public (unauthenticated) to allow external monitoring and orchestrator (Docker/K8s) health checks.
-   **Rate Limiting:** Implement a global limit (default: 20 req/min) via `slowapi` and Redis to prevent quota exhaustion and abuse.
-   **Credential Safety:** NEVER hardcode API keys. Use `os.getenv` or `pydantic-settings`. Leaked keys must be immediately rotated and marked as exhausted in the rotator.

### 2. State & Persistence
-   **Session Memory:** Use `RedisMemory` for chat history persistence.
-   **Graceful Degradation:** If Redis is unreachable, the system MUST fallback to stateless operation (empty history) rather than crashing.
-   **Deployment:** Use `docker-compose.dev.yml` for active development (volume mounts) and `docker-compose.prod.yml` for production (COPY source, resource limits).

### 3. Observability & Reliability
-   **Health Check Protocol:** All core components (Groq, Redis, Qdrant) MUST implement a `status()` method. The `/health` API aggregates these into a single report.
-   **Fail-Fast Search:** Qdrant Client timeout MUST be capped at **5 seconds** to ensure responsive graceful degradation when the vector store is under load.
-   **Structured Logging:** Standardized log prefixes MUST be used:
    - `[TOKEN_AUDIT]`: Usage monitoring.
    - `[REDIS_ERROR]`: Persistence issues (degraded state).
    - `[QDRANT_ERROR]`: Retrieval failures.
    - `[GROQ_ERROR]`: Utility/Generation failures.
    - `[PII]`: Scrubbing events.
-   **Error Handling:** Implement exponential backoff for external API calls and return user-friendly maintenance messages for known failure modes. Return HTTP 503 for backend service unavailability.

---

## Data Strategy & Quality Loop

### 1. Feedback Loop (Human-in-the-loop)
-   **UI Interaction:** Assistant messages phải bao gồm Thumbs Up/Down widgets và **Interactive Source Viewer** để tra cứu nhanh tài liệu gốc.
-   **Context Capture:** Every feedback entry MUST include the `original_query`, `bot_answer`, and the `raw_context` (retrieved chunks) used for generation.
-   **Persistent Audit:** Logs must be saved in real-time to `storage/feedback_audit.jsonl`. This file is the "ground truth" for future fine-tuning and system evaluation.

### 2. Timezone & Localization
-   **Standard:** All logs and timestamps MUST use **Vietnam Time (ICT / UTC+7)**.
-   **Implementation:** Explicitly use `timezone(timedelta(hours=7))` in Python logic to bypass container-level UTC defaults.

---

## Development Workflow
-   **Local Development:** Use Docker Compose for services. Hot-reload is enabled via bind mounts.
-   **Environment:** Maintain `.env` keys for Groq, Cohere, and LangSmith.
-   **Commits:** Focus messages on the "why" of pipeline adjustments.
