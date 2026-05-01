import os
from groq import Groq
import cohere
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from langsmith import traceable

from config.settings import settings
from src.core.analyzer import QueryAnalyzer
from src.core.rewriter import QueryRewriter
from src.core.context_builder import ContextBuilder
from src.core.generator import Generator
from src.core.resource_profile import ResourceProfile          # ← MỚI
from src.retrieval.engine import RetrievalStrategyEngine, RetrievalEngine
from src.retrieval.reranker import RerankPolicyEngine
from src.retrieval.cache import SemanticCache
from src.utils.text_utils import clean_text

IS_EVAL_MODE = os.getenv("EVAL_MODE", "false").lower() == "true"


class ProductionRAG:
    def __init__(self):
        self.groq_client   = Groq(api_key=settings.GROQ_API_KEY)
        self.cohere_client = cohere.Client(api_key=settings.COHERE_API_KEY)
        self.qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=60)

        self.dense_model  = SentenceTransformer("AITeamVN/Vietnamese_Embedding")
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

        self.analyzer  = QueryAnalyzer(self.groq_client)
        self.rewriter  = QueryRewriter(self.groq_client)
        self.retriever = RetrievalEngine(
            self.qdrant_client,
            self.dense_model,
            self.sparse_model,
        )
        self.policy    = RerankPolicyEngine(self.cohere_client)
        self.generator = Generator(self.groq_client)

        self.memory = []
        self.cache  = SemanticCache(threshold=0.90)

        if IS_EVAL_MODE:
            print("[Orchestration] EVAL_MODE=true → Semantic Cache bị tắt hoàn toàn.")
        else:
            self.cache.validate_and_clean()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def clear_memory(self) -> None:
        self.memory = []

    def clear_cache(self) -> None:
        self.cache.clear()

    def _get_formatted_history(self) -> str:
        if not self.memory:
            return "Không có."
        return "\n".join(
            f"User: {m['user']}\nBot: {m['bot']}" for m in self.memory
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
            response = self.groq_client.chat.completions.create(
                model=settings.UTILITY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=200,
            )
            lines = response.choices[0].message.content.strip().split("\n")
            sub_queries = [
                l.strip().lstrip("0123456789.-) ").strip()
                for l in lines
                if l.strip() and len(l.strip()) > 5
            ]
            if len(sub_queries) >= 2:
                sub_queries = sub_queries[:3]   # cap tại 3 tránh latency spike
                print(f"  [Decompose] {len(sub_queries)} sub-queries (capped at 3):")
                for i, sq in enumerate(sub_queries, 1):
                    print(f"    {i}. {sq}")
                return sub_queries
        except Exception as e:
            print(f"  [Decompose] Lỗi → fallback: {e}")

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
        print(f"  [Merge] {total_in} docs → {len(merged)} sau dedup")
        return merged

    # ── Core Pipeline ─────────────────────────────────────────────────────────

    @traceable(run_type="chain", name="RAG_Core_Pipeline")
    def process_with_context(self, raw_query: str) -> tuple[str, str]:
        query       = clean_text(raw_query)
        history_str = self._get_formatted_history()

        # ── Embedding ─────────────────────────────────────────────────────────
        query_embedding = self.dense_model.encode(query).tolist()

        # ── Semantic Cache ────────────────────────────────────────────────────
        if not IS_EVAL_MODE:
            cached_answer = self.cache.check(query_embedding)
            if cached_answer:
                self.memory.append({"user": query, "bot": cached_answer})
                return cached_answer, "⚡ Semantic Cache Hit"

        # ── Query Analysis ────────────────────────────────────────────────────
        analysis = self.analyzer.analyze(query, history_str)

        # ── TOKEN AUDIT: log ngay sau analysis để debug dễ hơn ───────────────
        print(
            f"[TOKEN_AUDIT] complexity={analysis.complexity_score:.2f} "
            f"| intent={analysis.intent} "
            f"| cache_entries={len(self.cache.cache_data)} "
            f"| history_turns={len(self.memory)}"
        )

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

                MULTI_CHUNK_BUDGET = 15
                fetch_k_per_sq     = max(5, MULTI_CHUNK_BUDGET // n_topics)
                print(
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
                    print(f"  [SubQuery] '{sq[:55]}' → {len(sq_docs)} docs")
                    docs_per_sq.append(sq_docs)

                raw_docs = self._merge_docs(docs_per_sq)

            # ── SINGLE-TOPIC PATH ─────────────────────────────────────────────
            else:
                n_topics = 1
                profile_for_rewrite = ResourceProfile.from_complexity(
                    analysis.complexity_score, n_topics=1
                )
                if profile_for_rewrite.skip_rewrite:
                    search_query = query
                    print(
                        f"  [Rewriter] SKIP — tier={profile_for_rewrite.tier} "
                        f"(complexity={analysis.complexity_score:.2f} < 0.30)"
                    )
                else:
                    search_query = self.rewriter.rewrite(query, analysis, history_str)

                raw_docs = self.retriever.search(search_query, strategy, fetch_k)

            print(f"[DEBUG] raw_docs    : {len(raw_docs)} docs | n_topics={n_topics}")

            # ── ResourceProfile TRƯỚC rerank: single source of truth ──────────
            profile = ResourceProfile.from_complexity(
                analysis.complexity_score, n_topics=n_topics
            )
            print(profile.log_summary())

            # ── Rerank ────────────────────────────────────────────────────────
            ranked_docs = self.policy.apply_policy(
                query, raw_docs, analysis,
                n_topics=n_topics,
                top_k_override=profile.rerank_top_k,
            )

            print(f"[DEBUG] ranked_docs : {len(ranked_docs)} docs after policy")

            if not ranked_docs and raw_docs:
                print("[WARN]  Fallback raw_docs[:3]")
                ranked_docs = raw_docs[:3]

            # ── Build Context (BUG FIX 1) ─────────────────────────────────────
            final_context = ContextBuilder.build(ranked_docs, profile=profile)

            print(
                f"[TOKEN_AUDIT] ctx_chars={len(final_context)} "
                f"| ctx_budget={profile.max_context_chars} "
                f"| tier={profile.tier}"
            )

            # ── Generate (BUG FIX 2) ──────────────────────────────────────────
            if not final_context:
                final_answer = "Hệ thống chưa có tài liệu về vấn đề này."
            else:
                final_answer = self.generator.generate(
                    original_query    = query,
                    context           = final_context,
                    complexity        = profile.complexity,
                    prompt_tier       = profile.prompt_tier,
                    max_output_tokens = profile.max_output_tokens,
                )

        # ── Cache Write ───────────────────────────────────────────────────────
        if not IS_EVAL_MODE and final_context and analysis.intent != "general":
            self.cache.add(query, query_embedding, final_answer)

        # ── Memory ────────────────────────────────────────────────────────────
        self.memory.append({"user": query, "bot": final_answer})
        if len(self.memory) > 3:
            self.memory.pop(0)

        return final_answer, final_context

    def process(self, raw_query: str) -> str:
        answer, _ = self.process_with_context(raw_query)
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