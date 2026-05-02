"""
cache_v2.py — Multi-Stage Cache System (v2)

Upgrade từ cache.py (1-tier JSON O(n)):

  Stage 1 — Embedding Cache   : In-memory LRU, TTL 7 ngày
  Stage 2 — Rewrite Cache     : In-memory LRU, TTL 3 ngày
  Stage 3 — Semantic Gen Cache: Qdrant ANN + L1 LRU, TTL 2 ngày, context-aware

Tại sao dùng Qdrant thay Redis + FAISS:
  - Qdrant đã deploy trong docker-compose → không thêm infra
  - ANN search thay thế O(n) linear scan
  - Persistent qua restart, TTL tự kiểm soát
  - Collection "semantic_cache" tách biệt "techcorp_knowledge"

Bỏ Retrieval Cache (Stage 2 trong proposal gốc):
  - Risk stale docs cao nếu tài liệu update
  - Qdrant query ~5-50ms → ROI không đáng
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any

from langsmith import traceable
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

# Phrases that must never be cached (bad / fallback answers)
NO_CACHE_PHRASES = [
    "hệ thống chưa có tài liệu",
    "không có tài liệu",
    "không có thông tin",
    "không tìm thấy",
    "không đủ thông tin",
    "xin chào! tôi là hệ thống",
    "tôi là hệ thống ai nội bộ",
]


# ─────────────────────────────────────────────────────────────────────────────
# LRU Base — shared by Stage 1 & 2
# ─────────────────────────────────────────────────────────────────────────────

class _LRUCache:
    """
    In-memory LRU with per-entry TTL.
    OrderedDict giữ insertion order → popitem(last=False) evicts LRU.
    """

    def __init__(self, max_size: int, ttl_seconds: float) -> None:
        self._max  = max_size
        self._ttl  = ttl_seconds
        self._data: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, exp = entry
        if time.time() > exp:
            del self._data[key]
            return None
        self._data.move_to_end(key)       # mark recently used
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (value, time.time() + self._ttl)
        if len(self._data) > self._max:
            self._data.popitem(last=False) # evict LRU

    def clear(self) -> None:
        self._data.clear()

    def stats(self) -> dict:
        now   = time.time()
        alive = sum(1 for _, (_, e) in self._data.items() if e > now)
        return {"size": len(self._data), "alive": alive, "max": self._max}


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Embedding Cache
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingCache:
    """
    Cache kết quả SentenceTransformer.encode() để tránh inference lại.

    Key  : MD5(normalize(query))
    Value: list[float] — 1024-dim vector
    TTL  : 7 ngày  (text không đổi → embedding không đổi)
    Win  : ~50–200 ms + CPU per hit
    """

    def __init__(self, max_size: int = 500, ttl_days: float = 7) -> None:
        self._cache  = _LRUCache(max_size, ttl_days * 86_400)
        self._hits   = 0
        self._misses = 0

    @staticmethod
    def _key(query: str) -> str:
        normalized = " ".join(query.lower().strip().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def get(self, query: str) -> list[float] | None:
        result = self._cache.get(self._key(query))
        if result is not None:
            self._hits += 1
            logger.debug(f"[EmbCache] HIT (total hits={self._hits})")
        else:
            self._misses += 1
        return result

    def set(self, query: str, embedding: list[float]) -> None:
        self._cache.set(self._key(query), embedding)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        total = self._hits + self._misses or 1
        return {
            **self._cache.stats(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total * 100:.1f}%",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Rewrite Cache
# ─────────────────────────────────────────────────────────────────────────────

class RewriteCache:
    """
    Cache kết quả QueryRewriter để tránh LLM call lặp lại.

    Key  : MD5(original_query)
    Value: rewritten_query string
    TTL  : 3 ngày
    Win  : ~500–2 000 ms + LLM tokens per hit
    """

    def __init__(self, max_size: int = 300, ttl_days: float = 3) -> None:
        self._cache  = _LRUCache(max_size, ttl_days * 86_400)
        self._hits   = 0
        self._misses = 0

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.md5(query.strip().encode()).hexdigest()

    def get(self, query: str) -> str | None:
        result = self._cache.get(self._key(query))
        if result is not None:
            self._hits += 1
            logger.debug(f"[RewriteCache] HIT → '{result[:60]}'")
        else:
            self._misses += 1
        return result

    def set(self, query: str, rewritten: str) -> None:
        # Không cache nếu rewriter không thay đổi gì
        if rewritten and rewritten.strip() != query.strip():
            self._cache.set(self._key(query), rewritten)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        total = self._hits + self._misses or 1
        return {
            **self._cache.stats(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total * 100:.1f}%",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Semantic Generation Cache (Qdrant-backed)
# ─────────────────────────────────────────────────────────────────────────────

class SemanticGenerationCache:
    """
    Semantic cache cho generation output — thay thế cache.py hoàn toàn.

    Nâng cấp so với cache.py:
      O(n) linear scan → Qdrant ANN (cosine, HNSW)
      No TTL           → TTL 2 ngày, check khi lookup
      No eviction      → max_entries guard + TTL cleanup on startup
      Not context-aware→ context_hash: MISS nếu docs thay đổi
      No L1            → L1 in-memory LRU (5 phút) cho hot queries

    Collection: "semantic_cache"  (tách biệt "techcorp_knowledge")
    Payload: query | answer | context_hash | created_at
    """

    COLLECTION  = "semantic_cache"
    VECTOR_SIZE = 1024           # Vietnamese_Embedding output dim

    def __init__(
        self,
        qdrant_client: QdrantClient,
        threshold: float  = 0.90,
        ttl_days: float   = 2.0,
        max_entries: int  = 2_000,
    ) -> None:
        self.db          = qdrant_client
        self.threshold   = threshold
        self.ttl_seconds = ttl_days * 86_400
        self.max_entries = max_entries

        self._hits                = 0
        self._misses              = 0
        self._context_mismatches  = 0
        self._expired_skips       = 0

        # L1: ultra-hot in-memory (5 min)
        self._l1 = _LRUCache(max_size=100, ttl_seconds=300)

        self._ensure_collection()

    # ── Qdrant bootstrap ──────────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        try:
            if not self.db.collection_exists(self.COLLECTION):
                self.db.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"[SemGenCache] Created Qdrant collection '{self.COLLECTION}'")
            else:
                n = self.db.count(self.COLLECTION).count
                logger.info(f"[SemGenCache] Loaded collection '{self.COLLECTION}' ({n} entries)")
        except Exception as exc:
            logger.error(f"[SemGenCache] Failed to init Qdrant collection: {exc}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def make_context_hash(context: str | None, chunk_ids: list[str] | None = None) -> str | None:
        """
        Hash của retrieved context để detect document updates.

        Ưu tiên dùng chunk_ids (stable hơn full text):
          - Full text có thể thay đổi do spacing, truncation → hash khác
          - Chunk IDs chỉ đổi khi documents thực sự update
        """
        if chunk_ids:
            # Sort để đảm bảo order-independent
            sorted_ids = sorted(chunk_ids)
            return hashlib.md5(",".join(sorted_ids).encode()).hexdigest()[:16]
        if context:
            # Fallback: normalize text (remove extra spaces) rồi hash
            normalized = " ".join(context.split())
            return hashlib.md5(normalized.encode()).hexdigest()[:16]
        return None

    @staticmethod
    def _l1_key(embedding: list[float]) -> str:
        """Approximate key for L1 using first 8 dims (fast, good enough)."""
        return str([round(x, 3) for x in embedding[:8]])

    # ── Public API ────────────────────────────────────────────────────────────

    @traceable(run_type="tool", name="Semantic_Cache_Check_v2")
    def check(
        self,
        query_embedding: list[float],
        context_hash: str | None = None,
    ) -> str | None:
        """
        Tìm cached answer gần nhất.

        context_hash (optional):
          - Cung cấp sau khi đã retrieve → HIT chỉ khi hash khớp.
            Nếu docs đã update → MISS tự động, trigger fresh generation.
          - None → pre-retrieval fast path, không check context.
        """
        # ── L1 fast path ──────────────────────────────────────────────────────
        l1_key = self._l1_key(query_embedding)
        l1_hit = self._l1.get(l1_key)
        if l1_hit is not None:
            self._hits += 1
            logger.info("  ⚡ [SemGenCache] L1 HIT (in-memory)")
            return l1_hit

        # ── Qdrant ANN ────────────────────────────────────────────────────────
        try:
            logger.info(f"[SemGenCache] Querying Qdrant — collection={self.COLLECTION}, threshold={self.threshold}")
            response = self.db.query_points(
                collection_name=self.COLLECTION,
                query=query_embedding,
                limit=3,
                with_payload=True,
            )
            results = response.points
            logger.info(f"[SemGenCache] Qdrant returned {len(results)} results")
            if results:
                logger.info(f"[SemGenCache] Top score: {results[0].score:.3f}")
        except Exception as exc:
            logger.warning(f"[SemGenCache] Qdrant query error: {exc}")
            return None

        now = time.time()

        for hit in results:
            if hit.score < self.threshold:
                break                          # sorted by score desc, no need to continue

            payload = hit.payload or {}

            # TTL check
            age = now - payload.get("created_at", 0)
            if age > self.ttl_seconds:
                self._expired_skips += 1
                logger.debug(f"[SemGenCache] EXPIRED (score={hit.score:.3f}, age={age/3600:.1f}h)")
                continue

            # Context-aware check (chỉ khi caller cung cấp context_hash)
            if context_hash is not None:
                cached_ctx_hash = payload.get("context_hash")
                if context_hash and cached_ctx_hash and cached_ctx_hash != context_hash:
                    self._context_mismatches += 1
                    logger.info(
                        f"[SemGenCache] CONTEXT_MISMATCH (score={hit.score:.3f}) "
                        "→ docs changed, forcing fresh retrieval"
                    )
                    continue

            answer = payload.get("answer", "")
            if answer:
                self._hits += 1
                self._l1.set(l1_key, answer)   # promote to L1
                logger.info(
                    f"  ⚡ [SemGenCache] Qdrant HIT "
                    f"score={hit.score:.3f} age={age/3600:.1f}h"
                )
                return answer

        self._misses += 1
        logger.info(f"[SemGenCache] MISS — no valid answer found (total_misses={self._misses})")
        return None

    def add(
        self,
        query: str,
        query_embedding: list[float],
        answer: str,
        context: str | None = None,
    ) -> None:
        """Persist answer. Skip nếu là fallback / error answer hoặc đã có entry tương tự."""
        norm = answer.strip().lower()
        for phrase in NO_CACHE_PHRASES:
            if phrase in norm:
                logger.debug(f"[SemGenCache] Skip — no-cache phrase detected")
                return

        ctx_hash = self.make_context_hash(context)

        # ── Semantic dedup: kiểm tra xem đã có entry gần giống chưa ──────────
        try:
            response = self.db.query_points(
                collection_name=self.COLLECTION,
                query=query_embedding,
                limit=1,
                with_payload=True,
            )
            similar = response.points
            if similar and similar[0].score >= self.threshold:
                existing = similar[0].payload or {}
                existing_answer = existing.get("answer", "")
                # Nếu answer giống nhau → skip (tránh duplicate)
                if existing_answer and self._answer_similarity(existing_answer, answer) > 0.85:
                    logger.debug(
                        f"[SemGenCache] Skip — semantic duplicate "
                        f"(score={similar[0].score:.3f})"
                    )
                    return
        except Exception:
            pass  # Nếu search lỗi, vẫn lưu (không block)

        try:
            self.db.upsert(
                collection_name=self.COLLECTION,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=query_embedding,
                        payload={
                            "query":        query,
                            "answer":       answer,
                            "context_hash": ctx_hash,
                            "created_at":   time.time(),
                        },
                    )
                ],
            )
            logger.debug(f"[SemGenCache] Stored '{query[:50]}...'")
        except Exception as exc:
            logger.warning(f"[SemGenCache] Failed to store entry: {exc}")

    @staticmethod
    def _answer_similarity(a1: str, a2: str) -> float:
        """Simple word-overlap similarity for dedup."""
        w1 = set(a1.lower().split())
        w2 = set(a2.lower().split())
        if not w1 or not w2:
            return 0.0
        return len(w1 & w2) / len(w1 | w2)

    def clear(self) -> None:
        """Drop + recreate collection, clear L1."""
        try:
            self.db.delete_collection(self.COLLECTION)
        except Exception:
            pass
        self._l1.clear()
        self._ensure_collection()
        logger.info("[SemGenCache] Cleared (Qdrant + L1)")

    def validate_and_clean(self) -> None:
        """
        Startup cleanup:
          1. Remove expired entries (created_at + ttl < now)
          2. Remove poisoned entries (NO_CACHE_PHRASES in answer)
          3. If oversized, purge oldest batch
        """
        try:
            total = self.db.count(self.COLLECTION).count
            if total == 0:
                logger.info("[SemGenCache] Empty — nothing to clean")
                return

            now          = time.time()
            to_delete    = []
            offset       = None

            while True:
                records, offset = self.db.scroll(
                    collection_name=self.COLLECTION,
                    limit=200,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for rec in records:
                    p          = rec.payload or {}
                    age        = now - p.get("created_at", 0)
                    answer_lc  = p.get("answer", "").lower()

                    is_expired  = age > self.ttl_seconds
                    is_poisoned = any(ph in answer_lc for ph in NO_CACHE_PHRASES)

                    if is_expired or is_poisoned:
                        reason = "expired" if is_expired else "poisoned"
                        logger.debug(f"[SemGenCache] Mark {reason}: '{p.get('query','')[:50]}'")
                        to_delete.append(rec.id)

                if offset is None:
                    break

            if to_delete:
                self.db.delete(
                    collection_name=self.COLLECTION,
                    points_selector=PointIdsList(points=to_delete),
                )
                logger.info(
                    f"[SemGenCache] validate_and_clean: "
                    f"removed {len(to_delete)}/{total} entries"
                )
            else:
                logger.info(f"[SemGenCache] validate_and_clean: {total} entries OK")

            # Oversized guard (simple: just log a warning for now)
            remaining = total - len(to_delete)
            if remaining > self.max_entries:
                logger.warning(
                    f"[SemGenCache] {remaining} entries > max {self.max_entries}. "
                    "Consider running manual purge or reducing TTL."
                )

        except Exception as exc:
            logger.warning(f"[SemGenCache] validate_and_clean error: {exc}")

    def stats(self) -> dict:
        try:
            n = self.db.count(self.COLLECTION).count
        except Exception:
            n = -1
        total = self._hits + self._misses or 1
        return {
            "qdrant_entries":      n,
            "l1_size":             self._l1.stats()["alive"],
            "hits":                self._hits,
            "misses":              self._misses,
            "context_mismatches":  self._context_mismatches,
            "expired_skips":       self._expired_skips,
            "hit_rate":            f"{self._hits / total * 100:.1f}%",
        }


# ─────────────────────────────────────────────────────────────────────────────
# MultiStageCache — single object used by orchestration.py
# ─────────────────────────────────────────────────────────────────────────────

class MultiStageCache:
    """
    Façade kết hợp 3 stage cache.

    Drop-in replacement cho SemanticCache cũ trong orchestration.py:

        # Trước
        self.cache = SemanticCache(threshold=0.90)

        # Sau
        self.cache = MultiStageCache(qdrant_client=self.qdrant_client)

    Integration points trong orchestration.py:
        1. Embedding   : cache.get_embedding / cache.store_embedding
        2. Rewrite     : cache.get_rewrite   / cache.store_rewrite
        3. Generation  : cache.check_generation / cache.store_generation
    """

    def __init__(
        self,
        qdrant_client: QdrantClient,
        sem_threshold: float = 0.78,
    ) -> None:
        self.embedding  = EmbeddingCache(max_size=500, ttl_days=7)
        self.rewrite    = RewriteCache(max_size=300,   ttl_days=3)
        self.generation = SemanticGenerationCache(
            qdrant_client=qdrant_client,
            threshold=sem_threshold,
            ttl_days=2,
            max_entries=2_000,
        )

    # ── Query Normalization ───────────────────────────────────────────────────

    @staticmethod
    def _normalize_for_cache(query: str) -> str:
        """
        Strip filler phrases tiếng Việt trước khi tính embedding cho cache.
        Mục tiêu: "mình muốn hỏi là X?" → "X?"

        Vấn đề gốc: filler words làm lệch embedding vector → cosine similarity
        của 2 câu cùng ý nhưng khác cách diễn đạt giảm từ ~0.88 xuống ~0.75,
        không qua được threshold → cache miss liên tục.

        Chỉ dùng cho cache key — KHÔNG ảnh hưởng đến retrieval hay generation.
        """
        import re
        q = query.strip()

        filler_patterns = [
            r'^mình muốn hỏi (là\s*)?',
            r'^tôi muốn hỏi[,:\s]*',
            r'^cho mình hỏi[,:\s]*',
            r'^cho tôi hỏi[,:\s]*',
            r'^xin hỏi[,:\s]*',
            r'^hỏi là[,:\s]*',
            r'^bạn ơi[,:\s]*',
            r'^mình ơi[,:\s]*',
            r'^ơi[,:\s]*',
            r'^em muốn hỏi[,:\s]*',
            r'^em hỏi[,:\s]*',
        ]
        for pattern in filler_patterns:
            q = re.sub(pattern, '', q, flags=re.IGNORECASE).strip()

        return q if q else query  # fallback to original if normalized is empty

    # ── Stage 1 helpers ───────────────────────────────────────────────────────

    def get_embedding(self, query: str) -> list[float] | None:
        return self.embedding.get(query)

    def store_embedding(self, query: str, embedding: list[float]) -> None:
        self.embedding.set(query, embedding)

    # ── Stage 2 helpers ───────────────────────────────────────────────────────

    def get_rewrite(self, query: str) -> str | None:
        return self.rewrite.get(query)

    def store_rewrite(self, query: str, rewritten: str) -> None:
        self.rewrite.set(query, rewritten)

    # ── Stage 3 helpers ───────────────────────────────────────────────────────

    def check_generation(
        self,
        query_embedding: list[float],
        context_hash: str | None = None,
    ) -> str | None:
        return self.generation.check(query_embedding, context_hash)

    def store_generation(
        self,
        query: str,
        query_embedding: list[float],
        answer: str,
        context: str | None = None,
    ) -> None:
        self.generation.add(query, query_embedding, answer, context)

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def make_context_hash(context: str) -> str | None:
        return SemanticGenerationCache.make_context_hash(context)

    def clear(self) -> None:
        self.embedding.clear()
        self.rewrite.clear()
        self.generation.clear()
        logger.info("[MultiStageCache] All stages cleared")

    def validate_and_clean(self) -> None:
        """Call on startup (replaces SemanticCache.validate_and_clean)."""
        self.generation.validate_and_clean()

    def stats(self) -> dict:
        return {
            "stage1_embedding":  self.embedding.stats(),
            "stage2_rewrite":    self.rewrite.stats(),
            "stage3_generation": self.generation.stats(),
        }

    @property
    def cache_data(self) -> list:
        """
        Backward-compatible property cho orchestration.py log line:
            len(self.cache.cache_data)

        Trả về list rỗng với len() = số entries trong Qdrant.
        Tránh thay đổi orchestration.py chỉ để fix 1 log line.
        """
        try:
            n = self.generation.db.count(self.generation.COLLECTION).count
            return [None] * n      # dummy list, chỉ cần len() đúng
        except Exception:
            return []

    def log_stats(self) -> None:
        s = self.stats()
        logger.info(
            "[MultiStageCache Stats]\n"
            f"  Embedding : {s['stage1_embedding']}\n"
            f"  Rewrite   : {s['stage2_rewrite']}\n"
            f"  Generation: {s['stage3_generation']}"
        )