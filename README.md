<div align="center">

# ⬡ KnowBot
### Internal Knowledge Base Agent · TechCorp

*Agentic RAG system that answers employee questions grounded strictly in internal documentation — no hallucination, full source traceability.*

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![LangSmith](https://img.shields.io/badge/Traced-LangSmith-orange?style=flat-square)](https://smith.langchain.com)
[![Qdrant](https://img.shields.io/badge/VectorDB-Qdrant-red?style=flat-square)](https://qdrant.tech)
[![Groq](https://img.shields.io/badge/LLM-Groq%20LLaMA3-purple?style=flat-square)](https://groq.com)
[![Docker](https://img.shields.io/badge/Infra-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docker.com)

</div>

---

## Why this exists

New employees at TechCorp lose hours searching through scattered Confluence pages, HR docs, and DevOps runbooks for answers that should take 30 seconds to find.

**KnowBot replaces that friction** with a conversational agent that retrieves, ranks, and generates answers from actual source documents — and tells you exactly which file it pulled from.

| Before | After |
|---|---|
| Search through 50+ Markdown files manually | Ask in natural Vietnamese, get answer in <10s |
| No guarantee answer is current or accurate | Strict faithfulness — no hallucination, source cited |
| Senior engineers answer repetitive questions | KnowBot handles Tier-1 IT/HR/Sales queries 24/7 |

---

## Architecture overview

```
┌─────────────────────────────── Docker Compose ─────────────────────────────────┐
│                                                                                 │
│   Streamlit :8501  ──HTTP──►  FastAPI :8000  ──►  RAG Pipeline                │
│                                                         │                       │
│                                               ┌─────────▼──────────┐           │
│                                               │  Qdrant :6333      │           │
│                                               │  techcorp_knowledge│           │
│                                               └────────────────────┘           │
│                                                                                 │
│   MinIO :9000/:9001  (raw .md document storage)                                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

External APIs
  ├── Groq      → LLaMA 3.3-70B  (analyzer · rewriter · generator)
  └── Cohere    → rerank-multilingual-v3.0
```

---

## Query pipeline — 7 stages

```
User query (Vietnamese natural language)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. SEMANTIC CACHE                                       │
│    Vietnamese_Embedding cosine · threshold 0.90         │
│    Disk-backed JSON · skip pipeline on HIT             │
└──────────────────────────┬──────────────────────────────┘
                           │ MISS
    ▼
┌─────────────────────────────────────────────────────────┐
│ 2. QUERY ANALYZER                                       │
│    intent (technical / general)                         │
│    complexity_score 0.0–1.0                            │
│    ambiguity_score  0.0–1.0                            │
│    entities [ ]                                         │
└──────────────────────────┬──────────────────────────────┘
                           │ intent = technical
    ▼
┌─────────────────────────────────────────────────────────┐
│ 3. QUERY REWRITER  (conditional)                        │
│    Triggers: complexity ≥ 0.5 OR ambiguity ≥ 0.4      │
│    Guard: rejects output if len > 2.5× original        │
│    Preserves domain terms (Weighted pipeline, Docker…) │
└──────────────────────────┬──────────────────────────────┘
    ▼
┌─────────────────────────────────────────────────────────┐
│ 4. HYBRID RETRIEVAL                                     │
│    Dense : Vietnamese_Embedding 1024d → Qdrant ANN      │
│    Sparse: Qdrant/BM25 (fastembed)                     │
│    Fusion: Reciprocal Rank Fusion (RRF) · top-20       │
└──────────────────────────┬──────────────────────────────┘
    ▼
┌─────────────────────────────────────────────────────────┐
│ 5. COHERE RERANKER                                      │
│    rerank-multilingual-v3.0                            │
│    Adaptive top-k: complexity < 0.3 → 2               │
│                    complexity < 0.65 → 3              │
│                    complexity ≥ 0.65 → 4              │
│    Fallback: raw_docs[:3] if reranker returns empty    │
└──────────────────────────┬──────────────────────────────┘
    ▼
┌─────────────────────────────────────────────────────────┐
│ 6. CONTEXT BUILDER                                      │
│    Deduplication (exact text match)                    │
│    Truncation at 12,000 chars                          │
│    Format: [Nguồn: filename]\n{text}\n---             │
└──────────────────────────┬──────────────────────────────┘
    ▼
┌─────────────────────────────────────────────────────────┐
│ 7. GENERATOR                                            │
│    Groq · LLaMA 3.3-70B-Versatile · T=0 · max 2048    │
│    Strict faithfulness prompt                          │
│    Preserves tables, warnings, blockquotes             │
│    Mandatory source citation per answer                │
└──────────────────────────┬──────────────────────────────┘
                           │
                    Answer + Source
```

---

## Ingestion pipeline

```
MinIO bucket "data" (.md files)
    │
    ▼
MetadataExtractor (2-tier)
    ├── Tier 1: path-based rules  (IT/, HR/, Sales/)       ← fast, high precision
    └── Tier 2: content scoring   (regex weighted scoring) ← fallback

    ▼
smart_markdown_chunker v4
    ├── Split on ## sections only (not ###)
    ├── Prepend section title into every sub-chunk
    ├── Table-aware split (preserves Markdown tables)
    ├── max_chunk_size = 1000 chars · overlap = 150
    └── Sliding window for oversized blocks

    ▼
Dual embedding
    ├── Dense : AITeamVN/Vietnamese_Embedding (1024d)
    └── Sparse: Qdrant/BM25 (fastembed)

    ▼
Qdrant upsert — collection "techcorp_knowledge"
    payload: chunk_id · document_id · source · text
             category · doc_type · security_level
```

---

## Evaluation pipeline

```
LangSmith dataset: TechCorp_IT_Onboarding_GT (15 QA pairs)
    │
    ▼
Stratified sampling: KMeans (5 clusters × 4 = ~20 samples)
    │
    ▼
RAG pipeline — EVAL_MODE=true
    ├── Semantic cache bypassed completely
    └── Memory cleared between samples

    ▼
┌────────────────────────┬───────────────────────────────┐
│  Embedding Recall      │  LLM Judge (1 call/sample)    │
│                        │                               │
│  GT < 15 words →       │  llama-3.1-8b-instant        │
│    keyword overlap     │                               │
│  GT ≥ 15 words →       │  context_precision  (float)  │
│    chunk cosine        │  strict_faithfulness (0/1)   │
│    threshold 0.55      │  answer_relevance   (float)  │
│    chunk_size = 200    │                               │
└────────────────────────┴───────────────────────────────┘
    │
    ▼
LangSmith experiment — TechCorp-RAG-Eval-v4
```

**Results**

| Metric | Score | Method |
|---|---|---|
| Context recall | **0.917** | Chunk-based cosine · Vietnamese_Embedding |
| Context precision | **0.775** | LLM judge · llama-3.1-8b-instant |
| Strict faithfulness | **0.917** | LLM judge · binary |
| Answer relevance | **0.942** | LLM judge · 0.0–1.0 |

---

## Tech stack

| Layer | Technology | Detail |
|---|---|---|
| **Dense embedding** | AITeamVN/Vietnamese_Embedding | 1024d · Vietnamese-optimized |
| **Sparse embedding** | Qdrant/BM25 via fastembed | Keyword signal for hybrid search |
| **Vector database** | Qdrant | Hybrid search · RRF fusion · payload filter |
| **Reranker** | Cohere rerank-multilingual-v3.0 | Cross-encoder · adaptive top-k |
| **LLM (production)** | Groq · LLaMA 3.3-70B-Versatile | Analyzer · rewriter · generator |
| **LLM (eval judge)** | Groq · LLaMA 3.1-8B-Instant | Cost-optimized · 1 call/sample |
| **Object storage** | MinIO (S3-compatible) | Raw .md document store |
| **API** | FastAPI + Uvicorn | REST endpoints · async startup |
| **UI** | Streamlit | Chat interface · session state |
| **Tracing** | LangSmith | Full pipeline observability |
| **Infra** | Docker Compose | Bind-mount volumes for hot reload |

---

## Project structure

```
techcorp_onboard_knowledge_base/
│
├── app.py                          # FastAPI entrypoint
├── streamlit_app.py                # Chat UI
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.ui
├── requirements.txt
│
├── config/
│   └── settings.py                 # Pydantic settings (env-based)
│
├── src/
│   ├── schemas.py                  # Shared Pydantic models
│   │
│   ├── pipelines/
│   │   └── orchestration.py        # ★ Main RAG pipeline (ProductionRAG)
│   │
│   ├── core/
│   │   ├── analyzer.py             # Query intent & complexity analysis
│   │   ├── rewriter.py             # Conditional query rewriting
│   │   ├── context_builder.py      # Context assembly & deduplication
│   │   └── generator.py            # Answer generation with LangSmith tracing
│   │
│   ├── retrieval/
│   │   ├── engine.py               # Hybrid retrieval (dense + sparse RRF)
│   │   ├── reranker.py             # Cohere adaptive rerank policy
│   │   └── cache.py                # Semantic cache (disk-backed JSON)
│   │
│   ├── ingestion/
│   │   ├── ingestion.py            # MinIO → chunk → embed → Qdrant
│   │   └── extractor.py            # 2-tier metadata extraction
│   │
│   └── utils/
│       └── text_utils.py           # Text cleaning utilities
│
├── evaluation/
│   ├── evaluator.py                # Full eval pipeline (LangSmith)
│   ├── eval_prompts.py             # Judge prompts (combined + legacy)
│   └── eval_schemas.py             # Pydantic schemas for judge output
│
└── storage/
    └── semantic_cache.json         # Persistent semantic cache (runtime)
```

---

## Running locally

**Prerequisites:** Docker · GROQ_API_KEY · COHERE_API_KEY · LANGSMITH_API_KEY

```bash
# 1. Clone
git clone https://github.com/MinHiuLe/techcorp_onboard_knowledge_base
cd techcorp_onboard_knowledge_base

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Start all services
docker compose up --build
```

| Service | URL |
|---|---|
| Chat UI | http://localhost:8501 |
| API docs | http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |
| MinIO console | http://localhost:9001 |

```bash
# 4. Upload documents to MinIO
# Drop .md files into the MinIO "data" bucket via http://localhost:9001

# 5. Run ingestion (one-time setup)
python -m src.ingestion.ingestion

# 6. Run evaluation
python -m evaluation.evaluator
# Results appear in LangSmith under prefix: TechCorp-RAG-Eval-v4
```

---

## Key design decisions

**Why hybrid search instead of dense-only?**

Vietnamese technical terms like `cấp phát thiết bị`, `BHXH`, or `AD account` have inconsistent dense embeddings — the model may not have seen them enough during pretraining. BM25 provides exact-match signal for acronyms and domain-specific proper nouns that dense vectors miss. RRF fusion keeps the best of both.

**Why conditional rewriting?**

Early versions rewrote every query, which caused domain-term hallucination — `"Weighted pipeline được tính như thế nào?"` became a verbose description of a generic weighted algorithm, causing Qdrant to retrieve completely wrong documents. The rewriter now triggers only above complexity/ambiguity thresholds and has an over-rewrite guard (reject output if > 2.5× input length).

**Why chunk-based embedding for recall metric?**

Encoding the full retrieved context as one vector dilutes signal — a 1500-char passage embedding is dominated by the average of all topics, not the specific fact matching a 6-word ground truth. Chunking to 200-char segments and taking max similarity gives recall 0.917 vs 0.000 with full-context encoding at threshold 0.75.

**Why bypass cache in eval mode?**

The semantic cache is disk-backed and persists across eval samples. Without `EVAL_MODE=true`, sample N+1 can hit a cache entry written by sample N, returning a stale answer with `context=""` — making the evaluator blind to actual retrieval quality. Bypass at the env-var level is cleaner than mocking.

**Why `smart_markdown_chunker` splits only on `##`, not `###`?**

Splitting on `###` created orphan chunks — `### Bước 1` sections contained no context about which process they belonged to. Keeping `###` subsections inside their parent `##` section, then prepending the section title into every sub-chunk, makes each chunk semantically self-contained for embedding.

---

## Environment variables

```env
# LLM
GROQ_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile

# Reranker
COHERE_API_KEY=...

# Vector DB
QDRANT_URL=http://localhost:6333
COLLECTION_NAME=techcorp_knowledge

# Object Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...

# Observability
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=techcorp-knowbot

# Runtime
EVAL_MODE=false   # set true during evaluation runs
```

---

## Roadmap

- [ ] Migrate semantic cache from JSON → Qdrant collection `semantic_cache`
- [ ] Expose `source` field in `ChatResponse` API schema
- [ ] Add document freshness tracking (updated_at → TTL-based cache invalidation)
- [ ] MLflow experiment tracking for ingestion hyperparameters (chunk_size, overlap)
- [ ] Expand LangSmith dataset beyond 15 QA pairs for more robust eval coverage

---

<div align="center">

Built by [MinHiuLe](https://github.com/MinHiuLe) · Powered by Groq · Qdrant · Cohere · LangSmith

</div>