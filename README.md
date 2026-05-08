# KnowBot — Internal Knowledge Base Agent

> A Retrieval-Augmented Generation (RAG) system for enterprise internal document lookup. Employees ask questions in natural Vietnamese and receive accurate, source-cited answers, fully based on internal documents — no hallucination.

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Qdrant](https://img.shields.io/badge/VectorDB-Qdrant-red?style=flat-square)](https://qdrant.tech)
[![Groq](https://img.shields.io/badge/LLM-Groq%20LLaMA3-purple?style=flat-square)](https://groq.com)
[![Docker](https://img.shields.io/badge/Infra-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docker.com)
[![LangSmith](https://img.shields.io/badge/Tracing-LangSmith-orange?style=flat-square)](https://smith.langchain.com)

---

## Table of Contents

- [Introduction](#introduction)
- [System Architecture](#system-architecture)
- [Question Processing Pipeline](#question-processing-pipeline)
- [Document Ingestion Pipeline](#document-ingestion-pipeline)
- [Project Structure](#project-structure)
- [Environment Requirements](#environment-requirements)
- [Installation and Running](#installation-and-running)
- [API Usage](#api-usage)
- [System Evaluation](#system-evaluation)
- [Environment Variables](#environment-variables)
- [Evaluation Results](#evaluation-results)

---

## Introduction

KnowBot solves the problem of employees spending too much time searching for information across dozens of scattered documents (IT policies, HR policies, security procedures, onboarding guides...).

| Problem | Solution |
|---|---|
| Manual search through 50+ Markdown files | Ask in Vietnamese, get an answer in < 10 seconds |
| No guarantee of information accuracy | Strict faithfulness — only uses data from documents, with source citations |
| Senior engineers answering repetitive questions | KnowBot handles Tier-1 IT/HR/Sales 24/7 |

---

## System Architecture

```
┌───────────────────────────── Docker Compose ──────────────────────────────┐
│                                                                            │
│   Streamlit UI :8501  ──HTTP──►  FastAPI :8000  ──►  RAG Pipeline        │
│                                                          │                 │
│                                               ┌──────────▼─────────┐      │
│                                               │   Qdrant :6333     │      │
│                                               │  techcorp_knowledge│      │
│                                               │  semantic_cache    │      │
│                                               └────────────────────┘      │
│   MinIO :9000/:9001  (stores original .md files)                         │
│   Redis :6379        (session memory, feedback logs)                      │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

External APIs
  ├── Groq   → LLaMA 3.3-70B  (Analyzer · Rewriter · Generator)
  │            LLaMA 3.1-8B   (Utility tasks — fast, cheaper)
  └── Cohere → rerank-multilingual-v3.0
```

**Main Components:**

- **FastAPI** — REST API with rate limiting, API Key auth, PII scrubbing
- **Streamlit** — Chat UI with feedback (thumbs up/down)
- **Qdrant** — Vector database for hybrid search (dense + sparse) and semantic cache
- **MinIO** — Object storage for original `.md` documents
- **Redis** — Stores conversation history by session and feedback logs
- **Groq** — LLM provider (LLaMA 3.3-70B for generation, LLaMA 3.1-8B for utility)
- **Cohere** — Cross-encoder multilingual reranker

---

## Question Processing Pipeline

Each question goes through up to 8 steps following **Decision-Driven RAG** logic — steps are skipped if unnecessary to optimize latency:

```
Input question (Vietnamese)
        │
        ▼
1. GUARDRAILS
   ├── Prompt injection detection (regex patterns)
   └── PII scrubbing in output (phone, email, ID)

        │
        ▼
2. MULTI-STAGE CACHE
   ├── Stage 1 — Embedding Cache  (in-memory LRU, TTL 7 days)
   ├── Stage 2 — Rewrite Cache    (in-memory LRU, TTL 3 days)
   └── Stage 3 — Semantic Gen Cache (Qdrant ANN, threshold 0.90, TTL 2 days)
                 └── L1 in-memory LRU (TTL 5 minutes) for hot queries
                     → HIT: return result immediately, skip entire pipeline

        │ MISS
        ▼
3. QUERY ANALYZER  (LLaMA 3.1-8B via Groq)
   ├── intent: "general" (greetings) | "technical" (business)
   ├── complexity_score: 0.0–1.0
   │     < 0.30 → FAST tier    (single fact, 1 chunk)
   │     < 0.65 → STANDARD tier (single topic process)
   │     ≥ 0.65 → FULL tier    (multi-topic, policy comparison)
   ├── ambiguity_score: 0.0–1.0
   └── entities: [ technical keywords ]

        │
        ▼
4. RESOURCE PROFILER  (ResourceProfile.from_complexity)
   Calculates budget for entire pipeline:
   ├── max_output_tokens  (350 / 650 / 800–1200 by tier)
   ├── max_context_chars  (1800 / 2800 / 12000 by tier)
   ├── rerank_top_k       (2–4 / 3–6 / 4–10 by tier)
   └── skip_rewrite       (True for FAST tier)

        │
        ▼
5. QUERY REWRITER  (LLaMA 3.1-8B via Groq — skipped if FAST)
   Triggers: complexity ≥ 0.58 OR ambiguity ≥ 0.4
   Guards:
   ├── Reject if output > 2.5× input (over-rewrite)
   └── Reject if adding scope-narrowing clauses ("to prevent X")

        │
        ▼
6. HYBRID RETRIEVAL
   ├── Dense : AITeamVN/Vietnamese_Embedding (1024d) → Qdrant ANN
   ├── Sparse: Qdrant/BM25 (fastembed) → keyword matching
   ├── Fusion: Reciprocal Rank Fusion (RRF) — fetch_k = 30
   └── Multi-topic path: decompose → parallel search → merge + dedup

        │
        ▼
7. COHERE RERANKER
   └── rerank-multilingual-v3.0, adaptive top-k by tier
       Fallback: raw_docs[:3] if Cohere fails

        │
        ▼
8. CONTEXT BUILDER
   ├── Deduplication (exact text match)
   ├── Per-chunk truncation (preserve Markdown tables)
   └── Format: [Source: filename]\n{text}\n---

        │
        ▼
9. GENERATOR  (LLaMA 3.3-70B via Groq, T=0)
   ├── FAST prompt: short answer, full listing
   ├── STANDARD prompt: cover all key points
   └── FULL prompt: anti-hallucination checklist, accurate table reading

        │
        ▼
    Answer + Source + Latency
```

**Multi-topic detection:** If the query has ≥ 2 `?` marks or complexity ≥ 0.8, the system automatically splits into up to 3 sub-queries, searches in parallel, merges results, then synthesizes the answer.

---

## Document Ingestion Pipeline

```
.md files in MinIO bucket "data"
        │
        ▼
MetadataExtractor (2 tiers)
    ├── Tier 1: Path-based rules  (IT/, HR/, Sales/)   — fast, high accuracy
    └── Tier 2: Content scoring   (regex weighted)     — fallback

        │
        ▼
smart_markdown_chunker
    ├── Split at ## section (do not split ###)
    ├── Prepend section title to each sub-chunk
    ├── Table-aware: keep Markdown tables intact, avoid cutting between rows
    ├── max_chunk_size = 1000 characters, overlap = 150 characters
    └── Sliding window for overly long blocks

        │
        ▼
Dual embedding (batch)
    ├── Dense : AITeamVN/Vietnamese_Embedding (1024d)
    └── Sparse: Qdrant/BM25 (fastembed)

        │
        ▼
Qdrant upsert — collection "techcorp_knowledge"
    payload: chunk_id · document_id · source · text
             category · doc_type · security_level
```

**Why only split at `##` (not `###`):** Splitting at `###` creates orphan chunks — for example `### Step 1` has no context about which process it belongs to. Keeping `###` within its parent `##` and prepending the section title helps each chunk be self-contained when embedded.

---

## Project Structure

```
knowbot/
│
├── app.py                      # FastAPI entrypoint — routes, middleware, lifespan
├── streamlit_app.py            # Chat UI — render messages, feedback widget
├── settings.py                 # Pydantic Settings — reads from .env
├── schemas.py                  # Shared Pydantic models
│
├── orchestration.py            # ★ Core RAG pipeline (ProductionRAG)
│
├── analyzer.py                 # Query analysis — intent, complexity, entities
├── rewriter.py                 # Conditional query rewriting with guards
├── context_builder.py          # Context assembly, dedup, budget-aware truncation
├── generator.py                # Answer generation with tiered prompts
├── resource_profile.py         # ResourceProfile — single source of truth for budget
│
├── engine.py                   # Hybrid retrieval (dense + sparse RRF)
├── reranker.py                 # Cohere adaptive rerank policy
├── cache.py                    # Multi-stage cache (Embedding + Rewrite + Semantic)
│
├── ingestion.py                # MinIO → chunk → embed → Qdrant
├── extractor.py                # 2-tier metadata extraction
│
├── redis_memory.py             # Session memory and feedback log
├── pii_scrubber.py             # Regex scrub phone, email, ID in output
├── text_utils.py               # Unicode normalization, JSON extraction
│
├── evaluator.py                # Eval pipeline — LangSmith + Gemma judge
├── eval_prompts.py             # Unified judge prompt (1 call/sample)
├── eval_schemas.py             # Pydantic schemas for evaluator output
├── eval_results.json           # Sample eval results
│
├── docker-compose.yml          # Production compose
├── docker-compose.dev.yml      # Dev compose (volume mount, hot reload)
├── docker-compose.prod.yml     # Prod compose (resource limits)
└── requirements.txt
```

---

## Environment Requirements

| Requirement | Details |
|---|---|
| Python | 3.11+ |
| Docker & Docker Compose | >= 24.0 |
| GROQ_API_KEY | [console.groq.com](https://console.groq.com) — free tier is sufficient |
| COHERE_API_KEY | [cohere.com](https://cohere.com) — trial key for reranker |
| LANGSMITH_API_KEY | [smith.langchain.com](https://smith.langchain.com) — optional, for tracing |

---

## Installation and Running

### 1. Clone repository

```bash
git clone https://github.com/MinHiuLe/techcorp_onboard_knowledge_base
cd techcorp_onboard_knowledge_base
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the values:

```env
GROQ_API_KEY=gsk_...
COHERE_API_KEY=...
MINIO_ACCESS_KEY=your_minio_user
MINIO_SECRET_KEY=your_minio_password

# Optional
LANGSMITH_API_KEY=...
API_KEYS=your_secret_key_1,your_secret_key_2
```

### 3. Start all services

```bash
# Production (no hot reload)
docker compose up --build

# Development (hot reload, bind mount code)
docker compose -f docker-compose.dev.yml up --build
```

Wait until you see the log: `RAG system is ready to receive requests!`

### 4. Check services

| Service | URL | Description |
|---|---|---|
| Chat UI | http://localhost:8501 | Streamlit chat interface |
| API | http://localhost:8000/docs | Swagger UI — test API directly |
| Health check | http://localhost:8000/health | Status of all components |
| Qdrant dashboard | http://localhost:6333/dashboard | Manage vector collections |
| MinIO console | http://localhost:9001 | Upload/manage documents |

### 5. Ingest documents into the system

**Step 5a — Upload documents to MinIO:**

Visit http://localhost:9001, log in with `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`, create a bucket named `data`, and upload `.md` files.

**Step 5b — Run ingestion pipeline:**

```bash
# Run directly (requires services to be running)
docker compose exec api python -m src.ingestion.ingestion

# Or run locally (requires requirements.txt)
pip install -r requirements.txt
python ingestion.py
```

Ingestion will: read all `.md` files from MinIO → chunk → embed → upsert into Qdrant.

> **Note:** Running ingestion again will delete and recreate the `techcorp_knowledge` collection from scratch.

---

## API Usage

All endpoints require the `X-API-Key` header if `API_KEYS` is configured in `.env`.

### Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_key" \
  -d '{
    "query": "What are the steps to grant Jira permissions?",
    "session_id": "user_123"
  }'
```

**Response:**
```json
{
  "answer": "The Jira permission granting process includes 5 steps: ...",
  "source": "Quy_trinh_Cap_quyen_Jira.md",
  "context": "[Source: ...]\n...",
  "latency_seconds": 2.35,
  "status": "success"
}
```

### Send feedback

```bash
curl -X POST http://localhost:8000/chat/feedback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_key" \
  -d '{
    "query": "What are the steps to grant Jira permissions?",
    "answer": "The process includes 5 steps...",
    "is_positive": true,
    "session_id": "user_123"
  }'
```

### Delete conversation history

```bash
curl -X DELETE http://localhost:8000/chat/memory/user_123
```

### Health check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "components": {
    "qdrant": { "healthy": true, "message": "Connected" },
    "groq":   { "healthy": true },
    "redis":  { "healthy": true, "message": "Connected" }
  },
  "cache": { "stage3_generation": { "hit_rate": "45.2%", ... } }
}
```

---

## System Evaluation

The evaluation pipeline uses **Gemma 4 31B** (Google AI Studio) as an independent LLM judge, avoiding same-family bias with the generator (LLaMA).

```bash
# Configure
export EVAL_MODE=true           # Disable semantic cache during eval
export GOOGLE_API_KEY=...       # Gemini/Gemma judge key

# Run eval
python evaluator.py
```

**Mechanism:**

1. **Stratified sampling** — KMeans clustering 10 groups × 5 samples = 50 representative questions
2. **Unified judge** — 1 LLM call per sample instead of 3, evaluating 4 metrics simultaneously
3. **Heuristic answer relevance** — Embedding similarity instead of LLM to avoid bias
4. **Auto-penalty** — Automatically deduct points for "no information" cases when GT clearly exists

**Metrics:**

| Metric | Measures |
|---|---|
| `context_recall` | Does retrieval fetch enough information from documents? |
| `context_precision` | Ratio of useful context (no noise) |
| `strict_faithfulness` | Does the generator hallucinate outside context? |
| `answer_completeness` | Does the generator use all information in context? |
| `answer_relevance` | Is the answer relevant to the question? (embedding-based) |

Results are automatically logged to LangSmith with prefix `TechCorp-RAG-Eval-v6-Gemma4`.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | — | API key for LLM (Groq) |
| `COHERE_API_KEY` | ✅ | — | API key for reranker (Cohere) |
| `MINIO_ACCESS_KEY` | ✅ | — | MinIO username |
| `MINIO_SECRET_KEY` | ✅ | — | MinIO password |
| `QDRANT_URL` | | `http://localhost:6333` | Qdrant URL |
| `REDIS_URL` | | `redis://localhost:6379/0` | Redis URL |
| `MINIO_ENDPOINT` | | `localhost:9000` | MinIO endpoint |
| `LLM_MODEL` | | `llama-3.3-70b-versatile` | Generation model |
| `UTILITY_MODEL` | | `llama-3.1-8b-instant` | Model for analyzer/rewriter |
| `COLLECTION_NAME` | | `techcorp_knowledge` | Qdrant collection |
| `API_KEYS` | | `""` | Comma-separated API keys. Empty = no auth required |
| `EVAL_MODE` | | `false` | Disable semantic cache when running evaluation |
| `LANGSMITH_API_KEY` | | `""` | LangSmith API key (optional) |
| `LANGSMITH_PROJECT` | | `TechCorp-RAG-Prod` | LangSmith project name |
| `GOOGLE_API_KEY` | | `""` | Gemini API key (only needed for evaluation) |

---

## Evaluation Results

Results on TechCorp's internal 15 QA pairs dataset (eval_results.json):

| Metric | Score | Method |
|---|---|---|
| Context Recall | **0.917** | Chunk cosine · Vietnamese_Embedding |
| Context Precision | **0.775** | LLM judge · Gemma 4 31B |
| Strict Faithfulness | **0.917** | LLM judge · binary |
| Answer Relevance | **0.942** | Embedding similarity · calibrated |

---

## Tech Stack

| Layer | Technology | Details |
|---|---|---|
| **Dense Embedding** | AITeamVN/Vietnamese_Embedding | 1024d, optimized for Vietnamese |
| **Sparse Embedding** | Qdrant/BM25 via fastembed | Keyword signal for hybrid search |
| **Vector DB** | Qdrant | Hybrid search, RRF fusion, semantic cache |
| **Reranker** | Cohere rerank-multilingual-v3.0 | Cross-encoder, adaptive top-k |
| **LLM Production** | Groq · LLaMA 3.3-70B-Versatile | Analyzer, Rewriter, Generator |
| **LLM Utility** | Groq · LLaMA 3.1-8B-Instant | Lightweight tasks, reduced latency |
| **LLM Eval Judge** | Google · Gemma 4 31B | Cross-family judge, avoids bias |
| **Object Storage** | MinIO (S3-compatible) | Stores original `.md` files |
| **Session Memory** | Redis | Conversation history, feedback queue |
| **API** | FastAPI + Uvicorn | REST, async, rate limiting |
| **UI** | Streamlit | Chat interface, feedback widget |
| **Observability** | LangSmith | Full pipeline tracing |
| **Infra** | Docker Compose | Dev/Prod profiles, volume mounts |

---

Built by [MinHiuLe](https://github.com/MinHiuLe) · Powered by Groq · Qdrant · Cohere · LangSmith
