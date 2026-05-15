import os
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor
import cohere
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from langsmith import traceable
from config.groq_rotator import GroqRotatorClient as Groq
from config.settings import settings
from src.core.analyzer import QueryAnalyzer
from src.core.rewriter import QueryRewriter
from src.core.context_builder import ContextBuilder
from src.core.generator import Generator
from src.core.resource_profile import ResourceProfile
from src.retrieval.engine import RetrievalStrategyEngine, RetrievalEngine
from src.retrieval.reranker import RerankPolicyEngine
from src.retrieval.cache import MultiStageCache
from src.utils.text_utils import clean_text
from src.utils.redis_memory import RedisMemory
from src.utils.pii_scrubber import scrub

IS_EVAL_MODE = os.getenv("EVAL_MODE", "false").lower() == "true"
RAG_TIMING_LOGS = os.getenv("RAG_TIMING_LOGS", "true").lower() == "true"
RAG_PATTERN_B_LITE = os.getenv("RAG_PATTERN_B_LITE", "false").lower() == "true"
logger = logging.getLogger(__name__)


def _empty_timings() -> dict:
    return {
        "analyzer_ms": 0.0,
        "embedding_ms": 0.0,
        "generation_cache_check_ms": 0.0,
        "cache_lookup_ms": 0.0,
        "rewrite_ms": 0.0,
        "retrieval_ms": 0.0,
        "rerank_ms": 0.0,
        "generation_ms": 0.0,
        "total_ms": 0.0,
    }


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


class ProductionRAG:
    _INJECTION_PATTERNS = [
        re.compile(r"ignore (all |previous |above )?instructions", re.I),
        re.compile(r"forget (everything|all|your instructions)", re.I),
        re.compile(r"you are now", re.I),
        re.compile(r"act as (a|an)(?!y)\b", re.I),
        re.compile(r"jailbreak", re.I),
        re.compile(r"system prompt", re.I),
        re.compile(r"<\|.*?\|>"),
        re.compile(r"###\s*(instruction|system)", re.I),
    ]

    _INJECTION_RESPONSE = (
        "Yêu cầu này không được hỗ trợ. "
        "Vui lòng đặt câu hỏi liên quan đến tài liệu nội bộ TechCorp.",
        ""
    )

    def __init__(self):
        # ── LLM Clients ───────────────────────────────────────────────────────
        self.groq_client   = Groq(api_key=settings.GROQ_API_KEY)
        
        self.cohere_client = cohere.Client(api_key=settings.COHERE_API_KEY)
        self.qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=5)

        self.dense_model  = SentenceTransformer("AITeamVN/Vietnamese_Embedding")
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

        # ── Hybrid Strategy ───────────────────────────────────────────────────
        self.analyzer  = QueryAnalyzer(self.groq_client)
        self.rewriter  = QueryRewriter(self.groq_client)
        
        self.retriever = RetrievalEngine(
            self.qdrant_client,
            self.dense_model,
            self.sparse_model,
        )
        self.policy    = RerankPolicyEngine(self.cohere_client)
        
        # Generator: Giữ LLaMA 70B (Groq) để đảm bảo chất lượng câu trả lời
        self.generator = Generator(self.groq_client)

        self.memory = RedisMemory()
        self.cache  = MultiStageCache(
            qdrant_client=self.qdrant_client,
            sem_threshold=0.90,
        )

        if IS_EVAL_MODE:
            logger.info("[Orchestration] EVAL_MODE=true → Semantic Cache bị tắt hoàn toàn.")
        
        logger.info(f"[Orchestration] UTILITY: {settings.UTILITY_MODEL} (Groq) | GENERATOR: {settings.LLM_MODEL} (Groq)")

        if not IS_EVAL_MODE:
            self.cache.validate_and_clean()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Aggregated health status for all dependencies."""
        qdrant_healthy = False
        qdrant_msg = "Unknown"
        try:
            self.qdrant_client.get_collection(settings.COLLECTION_NAME)
            qdrant_healthy = True
            qdrant_msg = "Connected"
        except Exception as e:
            qdrant_msg = str(e)

        groq_status = self.groq_client.status()
        redis_status = self.memory.status()
        
        overall = qdrant_healthy and groq_status["healthy"] and redis_status["healthy"]

        return {
            "status": "healthy" if overall else "degraded",
            "components": {
                "qdrant": {"healthy": qdrant_healthy, "message": qdrant_msg},
                "groq": groq_status,
                "redis": redis_status,
            }
        }

    def _is_injection(self, query: str) -> bool:
        return any(pattern.search(query) for pattern in self._INJECTION_PATTERNS)

    def clear_memory(self, session_id: str = "default") -> None:
        self.memory.clear(session_id)

    def clear_cache(self) -> None:
        self.cache.clear() 

    def _get_formatted_history(self, session_id: str) -> str:
        history = self.memory.get_history(session_id)
        if not history:
            return "Không có."
        return "\n".join(
            f"User: {m['user']}\nBot: {m['bot']}" for m in history
        )

    def _lookup_generation_cache(self, query: str, profile, timings: dict, debug: dict, session_id: str):
        cache_stage_start = time.perf_counter()
        stage_start = time.perf_counter()
        try:
            query_embedding = self.cache.get_embedding(query)
        except Exception as e:
            logger.warning(f"  ⚠️ [Cache_ERROR] Embedding: {e}")
            query_embedding = None

        if query_embedding is None:
            query_embedding = self.dense_model.encode(query).tolist()
            try:
                self.cache.store_embedding(query, query_embedding)
            except Exception:
                pass
        timings["embedding_ms"] = _elapsed_ms(stage_start)

        cached_answer = None
        if not IS_EVAL_MODE:
            stage_start = time.perf_counter()
            try:
                cached_answer = self.cache.check_generation(
                    query_embedding,
                    min_tier=profile.tier,
                )
                timings["generation_cache_check_ms"] = _elapsed_ms(stage_start)
                if cached_answer:
                    debug["cache_hit"] = True
                    logger.info(f"  ⚡ [PreRetrievalCache] HIT ({session_id}) tier={profile.tier}")
            except Exception as e:
                timings["generation_cache_check_ms"] = _elapsed_ms(stage_start)
                logger.warning(f"  ⚠️ [Cache_ERROR] GenCache: {e}")

        timings["cache_lookup_ms"] = _elapsed_ms(cache_stage_start)
        return query_embedding, cached_answer

    def _rewrite_query(self, query: str, analysis, history_str: str, profile, timings: dict, debug: dict) -> str:
        if profile.skip_rewrite:
            timings["rewrite_ms"] = 0.0
            debug["rewrite_source"] = "skip"
            debug["rewrite_used"] = False
            return query

        debug["rewrite_attempted"] = True
        stage_start = time.perf_counter()
        try:
            search_query = self.cache.get_rewrite(query)
        except Exception:
            search_query = None

        if search_query is None:
            try:
                search_query = self.rewriter.rewrite(query, analysis, history_str)
                debug["rewrite_source"] = "llm"
                self.cache.store_rewrite(query, search_query)
            except Exception as e:
                logger.error(f"[GROQ_ERROR] Rewrite failed: {e}")
                search_query = query
                debug["rewrite_source"] = "fallback"
        else:
            debug["rewrite_source"] = "cache_hit"
            logger.info(f"  [RewriteCache] HIT → '{search_query[:60]}'")

        timings["rewrite_ms"] = _elapsed_ms(stage_start)
        debug["rewrite_used"] = bool(search_query and search_query.strip() != query.strip())
        return search_query

    # ── Multi-topic Helpers ───────────────────────────────────────────────────

    def _is_multi_topic(self, query: str, analysis) -> bool:
        return query.count("?") >= 2 or analysis.complexity_score >= 0.8

    def _decompose_query(self, query: str) -> list[str]:
        prompt = f"""Tách câu hỏi sau thành các câu hỏi ĐỘC LẬP, mỗi câu về MỘT CHỦ ĐỀ DUY NHẤT.
Yêu cầu:
- Tối đa 3 câu hỏi con. Nếu câu hỏi chỉ cần 1-2 truy vấn là đủ, KHÔNG tách thêm.
- Mỗi câu hỏi con trên 1 dòng riêng.
- Giữ nguyên từ khóa kỹ thuật (Docker, VPN, AnyConnect...).
- Câu hỏi con phải đủ ý để tìm kiếm độc lập.
- KHÔNG tách các điều kiện logic của cùng 1 chủ đề thành câu hỏi riêng.
- Chỉ trả về danh sách câu hỏi, KHÔNG đánh số, KHÔNG giải thích.

CÂU HỎI GỐC: {query}"""

        try:
            # Multi-topic decomposition: [TỐI ƯU] Dùng Groq để tách câu hỏi siêu nhanh
            response = self.groq_client.chat.completions.create(
                model=settings.UTILITY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = response.choices[0].message.content.strip()
            lines = content.split("\n")
            sub_queries = [
                l.strip().lstrip("0123456789.-) ").strip()
                for l in lines
                if l.strip() and len(l.strip()) > 5
            ]
            if len(sub_queries) >= 2:
                sub_queries = sub_queries[:3]   # cap tại 3 tránh latency spike
                logger.info(f"  [Decompose] {len(sub_queries)} sub-queries (capped at 3):")
                for i, sq in enumerate(sub_queries, 1):
                    logger.info(f"    {i}. {sq}")
                return sub_queries
        except Exception as e:
            logger.error(f"  [Decompose] Lỗi → fallback: {e}")

        return [query]

    def _merge_docs(self, docs_per_query: list[list[dict]]) -> list[dict]:
        
        count_map  = {}
        seen_texts = set()
        merged     = []

        for docs in docs_per_query:
            for doc in docs:
                txt = doc["text"]
                count_map[txt] = count_map.get(txt, 0) + 1
                if txt not in seen_texts:
                    seen_texts.add(txt)
                    merged.append(doc)

        merged.sort(key=lambda d: count_map[d["text"]], reverse=True)

        total_in = sum(len(d) for d in docs_per_query)
        logger.info(f"  [Merge] {total_in} docs → {len(merged)} sau dedup")
        return merged

    # ── Core Pipeline ─────────────────────────────────────────────────────────

    @traceable(run_type="chain", name="RAG_Core_Pipeline")
    def process_with_context(self, raw_query: str, session_id: str = "default") -> dict:
        start_time = time.time()
        perf_start = time.perf_counter()
        timings = _empty_timings()
        debug = {
            "intent": None,
            "cache_hit": False,
            "rewrite_attempted": False,
            "rewrite_used": False,
            "rewrite_source": "skip",
            "is_multi_topic": False,
            "route": "unknown",
            "top_k": None,
            "model_name": settings.LLM_MODEL,
        }
        metadata = {
            "tokens": {"total": 0, "prompt": 0, "completion": 0},
            "timings_ms": timings,
            "debug": debug,
        }

        def finish_metadata(route: str | None = None) -> dict:
            if route:
                debug["route"] = route
            timings["total_ms"] = _elapsed_ms(perf_start)
            metadata["latency"] = time.time() - start_time
            metadata["timings_ms"] = timings
            metadata["debug"] = debug
            metadata["cache_hit"] = debug["cache_hit"]
            if RAG_TIMING_LOGS:
                logger.info(
                    "[RAG_TIMING] session=%s route=%s intent=%s cache_hit=%s "
                    "rewrite_attempted=%s rewrite_used=%s rewrite_source=%s is_multi_topic=%s "
                    "top_k=%s model=%s timings=%s",
                    session_id,
                    debug["route"],
                    debug["intent"],
                    debug["cache_hit"],
                    debug["rewrite_attempted"],
                    debug["rewrite_used"],
                    debug["rewrite_source"],
                    debug["is_multi_topic"],
                    debug["top_k"],
                    debug["model_name"],
                    timings,
                )
            return metadata
        
        try:
            query       = clean_text(raw_query)
            if self._is_injection(query):
                logger.warning("[Guardrail] Injection attempt blocked | session=%s", session_id)
                return {
                    "answer": self._INJECTION_RESPONSE[0],
                    "context": "",
                    "metadata": finish_metadata("guardrail")
                }

            # --- REDIS GRACEFUL DEGRADATION ---
            try:
                history_str = self._get_formatted_history(session_id)
                history_len = len(self.memory.get_history(session_id))
            except Exception as e:
                logger.error(f"[REDIS_ERROR] Session={session_id} | {e}")
                history_str = "Không có (Lỗi kết nối Redis)."
                history_len = 0

            # ── Query Analysis & Resource Profiling ───────────────
            stage_start = time.perf_counter()
            try:
                analysis = self.analyzer.analyze(query, history_str)
                timings["analyzer_ms"] = _elapsed_ms(stage_start)
            except Exception as e:
                timings["analyzer_ms"] = _elapsed_ms(stage_start)
                logger.error(f"[GROQ_ERROR] Analysis failed: {e}")
                return {
                    "answer": "Hệ thống hiện đang quá tải hoặc gặp sự cố kết nối với AI Model (Groq). Vui lòng thử lại sau vài giây.",
                    "context": "",
                    "metadata": finish_metadata("analysis_error")
                }
            
            # ── TOKEN AUDIT ──────────────────────────────────────
            logger.info(
                f"[TOKEN_AUDIT] complexity={analysis.complexity_score:.2f} "
                f"| intent={analysis.intent} "
                f"| history_turns={history_len}"
            )

            # ── ResourceProfile: single source of truth ──────────
            is_multi = self._is_multi_topic(query, analysis)
            profile = ResourceProfile.from_complexity(
                analysis.complexity_score, 
                n_topics=3 if is_multi else 1
            )
            debug.update({
                "intent": analysis.intent,
                "is_multi_topic": is_multi,
                "top_k": profile.rerank_top_k,
            })

            if analysis.intent == "general":
                debug["route"] = "general"
                stage_start = time.perf_counter()
                try:
                    final_answer, gen_meta = self.generator.generate(
                        original_query    = query,
                        context           = "",
                        complexity        = profile.complexity,
                        prompt_tier       = "GENERAL",
                        max_output_tokens = profile.max_output_tokens,
                    )
                    metadata["tokens"] = gen_meta
                except Exception as e:
                    logger.error(f"[GROQ_ERROR] Generation failed: {e}")
                    final_answer = "Xin chĂ o! TĂ´i lĂ  há»‡ thá»‘ng AI ná»™i bá»™ TechCorp."
                timings["generation_ms"] = _elapsed_ms(stage_start)

                try:
                    self.memory.add_message(session_id, query, final_answer)
                except Exception as e:
                    logger.error(f"[REDIS_ERROR] Failed to save message: {e}")

                return {
                    "answer": final_answer,
                    "context": "",
                    "metadata": finish_metadata()
                }

            # Stage 1 — try embedding cache
            pattern_b_eligible = (
                RAG_PATTERN_B_LITE
                and analysis.intent == "technical"
                and not is_multi
                and not profile.skip_rewrite
            )
            search_query = None

            if pattern_b_eligible:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    cache_future = executor.submit(
                        self._lookup_generation_cache,
                        query,
                        profile,
                        timings,
                        debug,
                        session_id,
                    )
                    rewrite_future = executor.submit(
                        self._rewrite_query,
                        query,
                        analysis,
                        history_str,
                        profile,
                        timings,
                        debug,
                    )
                    query_embedding, cached_answer = cache_future.result()
                    search_query = rewrite_future.result()
            else:
                query_embedding, cached_answer = self._lookup_generation_cache(
                    query,
                    profile,
                    timings,
                    debug,
                    session_id,
                )

            if cached_answer:
                return {
                    "answer": cached_answer,
                    "context": "⚡ Pre-Retrieval Cache Hit",
                    "metadata": finish_metadata("cache_hit")
                }

            if analysis.intent == "general":
                debug["route"] = "general"
                stage_start = time.perf_counter()
                try:
                    final_answer, gen_meta = self.generator.generate(
                        original_query    = query,
                        context           = "",
                        complexity        = profile.complexity,
                        prompt_tier       = "GENERAL",
                        max_output_tokens = profile.max_output_tokens,
                    )
                    metadata["tokens"] = gen_meta
                except Exception as e:
                    logger.error(f"[GROQ_ERROR] Generation failed: {e}")
                    final_answer = "Xin chào! Tôi là hệ thống AI nội bộ TechCorp."
                timings["generation_ms"] = _elapsed_ms(stage_start)
                final_context = ""

            else:
                strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)

                # ── MULTI-TOPIC PATH ──────────────────────────────────────────────
                if is_multi:
                    debug["route"] = "technical_multi_topic"
                    stage_start = time.perf_counter()
                    try:
                        sub_queries = self._decompose_query(query)
                        n_topics    = len(sub_queries)

                        MULTI_CHUNK_BUDGET = 25
                        fetch_k_per_sq     = max(8, MULTI_CHUNK_BUDGET // n_topics)

                        dense_vecs = self.dense_model.encode(sub_queries)

                        docs_per_sq = []
                        for i, sq in enumerate(sub_queries):
                            sq_docs = self.retriever.search_with_vec(
                                sq, dense_vecs[i].tolist(), strategy, fetch_k_per_sq
                            )
                            docs_per_sq.append(sq_docs)

                        raw_docs = self._merge_docs(docs_per_sq)
                        timings["retrieval_ms"] = _elapsed_ms(stage_start)
                    except Exception as e:
                        timings["retrieval_ms"] = _elapsed_ms(stage_start)
                        logger.error(f"[QDRANT_ERROR] Multi-topic search failed: {e}")
                        return {
                            "answer": "Hệ thống tìm kiếm (Qdrant) hiện đang gặp sự cố. Chúng tôi đang tiến hành bảo trì hạ tầng dữ liệu.",
                            "context": "",
                            "metadata": finish_metadata("retrieval_error")
                        }


                # ── SINGLE-TOPIC PATH ─────────────────────────────────────────────
                else:
                    debug["route"] = "technical_single_topic"
                    n_topics = 1
                    if search_query is None:
                        search_query = self._rewrite_query(query, analysis, history_str, profile, timings, debug)

                    stage_start = time.perf_counter()
                    try:
                        raw_docs = self.retriever.search(search_query, strategy, fetch_k)
                        timings["retrieval_ms"] = _elapsed_ms(stage_start)
                    except Exception as e:
                        timings["retrieval_ms"] = _elapsed_ms(stage_start)
                        logger.error(f"[QDRANT_ERROR] Search failed: {e}")
                        return {
                            "answer": "Hệ thống tìm kiếm (Qdrant) hiện đang gặp sự cố. Chúng tôi đang tiến hành bảo trì hạ tầng dữ liệu.",
                            "context": "",
                            "metadata": finish_metadata("retrieval_error")
                        }


                # ── Rerank ────────────────────────────────────────────────────────
                stage_start = time.perf_counter()
                try:
                    ranked_docs = self.policy.apply_policy(
                        query, raw_docs, analysis,
                        n_topics=n_topics,
                        top_k_override=profile.rerank_top_k,
                    )
                    timings["rerank_ms"] = _elapsed_ms(stage_start)
                except Exception as e:
                    timings["rerank_ms"] = _elapsed_ms(stage_start)
                    logger.error(f"[COHERE_ERROR] Rerank failed: {e}")
                    ranked_docs = raw_docs[:3] # Fallback to raw

                if not ranked_docs and raw_docs:
                    ranked_docs = raw_docs[:3]

                # ── Build Context ────────────────────────────────────────────────
                final_context = ContextBuilder.build(ranked_docs, profile=profile)

                # ── Generate ─────────────────────────────────────────────────────
                if not final_context:
                    logger.info("[Guardrail] Off-topic blocked | session=%s", session_id)
                    final_answer = (
                        "Xin lỗi, câu hỏi này nằm ngoài phạm vi tài liệu nội bộ TechCorp. "
                        "Tôi chỉ có thể hỗ trợ các vấn đề về IT, HR và Sales."
                    )
                else:
                    stage_start = time.perf_counter()
                    try:
                        final_answer, gen_meta = self.generator.generate(
                            original_query    = query,
                            context           = final_context,
                            complexity        = profile.complexity,
                            prompt_tier       = profile.prompt_tier,
                            max_output_tokens = profile.max_output_tokens,
                        )
                        metadata["tokens"] = gen_meta
                        timings["generation_ms"] = _elapsed_ms(stage_start)
                    except Exception as e:
                        timings["generation_ms"] = _elapsed_ms(stage_start)
                        logger.error(f"[GROQ_ERROR] Generation failed: {e}")
                        return {
                            "answer": "Hệ thống hiện đang gặp sự cố khi tạo câu trả lời. Vui lòng thử lại sau.",
                            "context": "",
                            "metadata": finish_metadata("generation_error")
                        }

            # ── Cache Write & Memory ──────────────────────────────────────────────
            if not IS_EVAL_MODE and final_answer and analysis.intent != "general":
                try:
                    self.cache.store_generation(
                        query           = query, 
                        query_embedding = query_embedding, 
                        answer          = final_answer, 
                        context         = final_context,
                        complexity      = profile.complexity,
                        tier            = profile.tier
                    )
                except Exception: pass

            try:
                self.memory.add_message(session_id, query, final_answer)
            except Exception as e:
                logger.error(f"[REDIS_ERROR] Failed to save message: {e}")

            return {
                "answer": final_answer,
                "context": final_context,
                "metadata": finish_metadata()
            }

        except Exception as e:
            logger.critical(f"[CRITICAL_ERROR] Unexpected pipeline failure: {e}")
            return {
                "answer": "Đã xảy ra lỗi hệ thống nghiêm trọng. Chúng tôi đã ghi nhận sự cố.",
                "context": "",
                "metadata": finish_metadata("critical_error")
            }

    @traceable(run_type="chain", name="RAG_Streaming_Pipeline")
    def process_with_context_stream(self, raw_query: str, session_id: str = "default"):
        """
        Safe streaming adapter around process_with_context.
        The sync pipeline remains the source of truth for LangSmith token
        usage, generation-cache writes, and Redis memory.
        """
        result = self.process_with_context(raw_query, session_id=session_id)
        answer = result.get("answer", "")
        context = result.get("context", "")
        scrubbed = scrub(answer)
        if scrubbed.hits > 0:
            logger.warning("[PII] %d match(es) scrubbed | session=%s", scrubbed.hits, session_id)
        answer = scrubbed.text

        chunk_size = 48
        for start in range(0, len(answer), chunk_size):
            yield answer[start:start + chunk_size], context
        return

    def process(self, raw_query: str, session_id: str = "default") -> str:
        result = self.process_with_context(raw_query, session_id)
        return result["answer"]


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("🚀 TECHCORP DECISION-DRIVEN RAG (CLI MODE)")
    print("#" * 60)
    print("Gõ 'exit', 'q', hoặc 'quit' để thoát.\n")

    app = ProductionRAG()

    while True:
        user_input = input("👤 User: ")
        if user_input.lower() in ["exit", "q", "quit"]:
            print("Tạm biệt!")
            break
        try:
            result = app.process(user_input)
            print(f"\n🤖 Bot:\n{result}\n")
            print("-" * 50)
        except Exception as e:
            print(f"\n❌ [LỖI HỆ THỐNG]: {e}\n")
