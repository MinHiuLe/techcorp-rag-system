import os
import re
import logging
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

IS_EVAL_MODE = os.getenv("EVAL_MODE", "false").lower() == "true"
logger = logging.getLogger(__name__)


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
        self.qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=60)

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
    def process_with_context(self, raw_query: str, session_id: str = "default") -> tuple[str, str]:
        try:
            query       = clean_text(raw_query)
            if self._is_injection(query):
                logger.warning("[Guardrail] Injection attempt blocked | session=%s", session_id)
                return self._INJECTION_RESPONSE

            history_str = self._get_formatted_history(session_id)

            # ── Query Analysis & Resource Profiling ───────────────
            analysis = self.analyzer.analyze(query, history_str)
            
            # ── TOKEN AUDIT: log ngay sau analysis để debug dễ hơn ───────────────
            logger.info(
                f"[TOKEN_AUDIT] complexity={analysis.complexity_score:.2f} "
                f"| intent={analysis.intent} "
                f"| history_turns={len(self.memory.get_history(session_id))}"
            )

            # ── ResourceProfile: single source of truth ──────────
            profile = ResourceProfile.from_complexity(
                analysis.complexity_score, 
                n_topics=3 if self._is_multi_topic(query, analysis) else 1
            )

            # Stage 1 — try embedding cache first (saves ~100ms SentenceTransformer)
            try:
                query_embedding = self.cache.get_embedding(query)
            except Exception as e:
                logger.warning(f"  ⚠️ [Cache] Error: {e}")
                query_embedding = None

            if query_embedding is None:
                query_embedding = self.dense_model.encode(query).tolist()
                try:
                    self.cache.store_embedding(query, query_embedding)
                except Exception:
                    pass

            # Stage 2 — try generation cache (context-aware if context known, else pre-retrieval)
            if not IS_EVAL_MODE:
                try:
                    # Pass profile.tier to ensure we don't hit a lower-tier cache
                    cached_answer = self.cache.check_generation(
                        query_embedding, 
                        min_tier=profile.tier
                    )
                    if cached_answer:
                        logger.info(f"  ⚡ [PreRetrievalCache] HIT ({session_id}) tier={profile.tier} — skipping retrieval + generation")
                        return cached_answer, "⚡ Pre-Retrieval Cache Hit"
                except Exception as e:
                    logger.warning(f"  ⚠️ [GenCache] Error: {e}")

            if analysis.intent == "general":
                final_answer  = "Xin chào! Tôi là hệ thống AI nội bộ TechCorp."
                final_context = ""

            else:
                strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)
                is_multi          = self._is_multi_topic(query, analysis)

                # ── MULTI-TOPIC PATH ──────────────────────────────────────────────
                if is_multi:
                    sub_queries = self._decompose_query(query)
                    n_topics    = len(sub_queries)

                    MULTI_CHUNK_BUDGET = 25  # Tăng budget cho 12k chars context
                    fetch_k_per_sq     = max(8, MULTI_CHUNK_BUDGET // n_topics)
                    logger.info(
                        f"  [Multi] n_topics={n_topics} "
                        f"→ fetch_k_per_sq={fetch_k_per_sq} (budget={MULTI_CHUNK_BUDGET})"
                    )

                    # Batch encode: 1 lần cho N sub-queries (tránh N lần encode riêng)
                    dense_vecs = self.dense_model.encode(sub_queries)   # (N, 1024)

                    docs_per_sq = []
                    for i, sq in enumerate(sub_queries):
                        sq_docs = self.retriever.search_with_vec(
                            sq, dense_vecs[i].tolist(), strategy, fetch_k_per_sq
                        )
                        logger.info(f"  [SubQuery] '{sq[:55]}' → {len(sq_docs)} docs")
                        docs_per_sq.append(sq_docs)

                    raw_docs = self._merge_docs(docs_per_sq)

                # ── SINGLE-TOPIC PATH ─────────────────────────────────────────────
                else:
                    n_topics = 1
                    if profile.skip_rewrite:
                        search_query = query
                        logger.info(
                            f"  [Rewriter] SKIP — tier={profile.tier} "
                            f"(complexity={analysis.complexity_score:.2f} < 0.30)"
                        )
                    else:
                   # Stage 2 — try rewrite cache (saves ~500ms LLM call)
                        try:
                            search_query = self.cache.get_rewrite(query)
                        except Exception:
                            search_query = None

                        if search_query is None:
                            search_query = self.rewriter.rewrite(query, analysis, history_str)
                            try:
                                self.cache.store_rewrite(query, search_query)
                            except Exception:
                                pass
                        else:
                            logger.info(f"  [RewriteCache] HIT → '{search_query[:60]}'")

                    raw_docs = self.retriever.search(search_query, strategy, fetch_k)

                logger.debug(f"[DEBUG] raw_docs    : {len(raw_docs)} docs | n_topics={n_topics}")

                # ── Rerank ────────────────────────────────────────────────────────
                ranked_docs = self.policy.apply_policy(
                    query, raw_docs, analysis,
                    n_topics=n_topics,
                    top_k_override=profile.rerank_top_k,
                )

                logger.debug(f"[DEBUG] ranked_docs : {len(ranked_docs)} docs after policy")

                if not ranked_docs and raw_docs:
                    logger.warning("[WARN]  Fallback raw_docs[:3]")
                    ranked_docs = raw_docs[:3]

                # ── Build Context (BUG FIX 1) ─────────────────────────────────────
                final_context = ContextBuilder.build(ranked_docs, profile=profile)

                logger.info(
                    f"[TOKEN_AUDIT] ctx_chars={len(final_context)} "
                    f"| ctx_budget={profile.max_context_chars} "
                    f"| tier={profile.tier}"
                )

                # ── Generate (BUG FIX 2) ──────────────────────────────────────────
                if not final_context:
                    logger.info("[Guardrail] Off-topic blocked | session=%s | query=%s",
                                session_id, query[:60])
                    final_answer = (
                        "Xin lỗi, câu hỏi này nằm ngoài phạm vi tài liệu nội bộ TechCorp. "
                        "Tôi chỉ có thể hỗ trợ các vấn đề về IT, HR và Sales."
                    )
                else:
                    final_answer = self.generator.generate(
                        original_query    = query,
                        context           = final_context,
                        complexity        = profile.complexity,
                        prompt_tier       = profile.prompt_tier,
                        max_output_tokens = profile.max_output_tokens,
                    )

            # ── Cache Write ───────────────────────────────────────────────────────
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
                    except Exception:
                        pass

            # ── Memory ────────────────────────────────────────────────────────────
            self.memory.add_message(session_id, query, final_answer)

            return final_answer, final_context

        except Exception as e:
            err_msg = f"❌ [Lỗi hệ thống]: {str(e)}"
            logger.error(err_msg)
            return "Hệ thống hiện đang gặp sự cố kết nối tới cơ sở dữ liệu (Qdrant/MinIO). Vui lòng kiểm tra lại hạ tầng Docker.", ""


    def process(self, raw_query: str, session_id: str = "default") -> str:
        answer, _ = self.process_with_context(raw_query, session_id)
        return answer


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
