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

    # ── Helpers ──────────────────────────────────────────────────────────────────

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

    # ── Core Pipeline ─────────────────────────────────────────────────────────────

    @traceable(run_type="chain", name="RAG_Core_Pipeline")
    def process_with_context(self, raw_query: str) -> tuple[str, str]:
        query       = clean_text(raw_query)
        history_str = self._get_formatted_history()

        query_embedding = self.dense_model.encode(query).tolist()

        # ── Semantic Cache ────────────────────────────────────────────────────────
        if not IS_EVAL_MODE:
            cached_answer = self.cache.check(query_embedding)
            if cached_answer:
                self.memory.append({"user": query, "bot": cached_answer})
                return cached_answer, "⚡ Semantic Cache Hit"

        # ── Query Analysis ────────────────────────────────────────────────────────
        analysis = self.analyzer.analyze(query, history_str)

        if analysis.intent == "general":
            final_answer  = "Xin chào! Tôi là hệ thống AI nội bộ TechCorp."
            final_context = ""

        else:
            # ── Rewrite ──────────────────────────────────────────────────────────
            search_query = self.rewriter.rewrite(query, analysis, history_str)

            # ── Retrieval ─────────────────────────────────────────────────────────
            strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)
            raw_docs = self.retriever.search(search_query, strategy, fetch_k)

            print(f"[DEBUG] raw_docs     : {len(raw_docs)} docs")

            # ── Rerank ────────────────────────────────────────────────────────────
            ranked_docs = self.policy.apply_policy(search_query, raw_docs, analysis)

            print(f"[DEBUG] ranked_docs  : {len(ranked_docs)} docs after policy")

            # Fallback: nếu rerank filter hết → giữ raw_docs top-3
            if not ranked_docs and raw_docs:
                print("[WARN]  apply_policy trả về rỗng → fallback raw_docs[:3]")
                ranked_docs = raw_docs[:3]

            # ── Build Context ─────────────────────────────────────────────────────
            final_context = ContextBuilder.build(ranked_docs)

            print(f"[DEBUG] final_context: {len(final_context)} chars")

            # ── Generate ──────────────────────────────────────────────────────────
            if not final_context:
                final_answer = "Hệ thống chưa có tài liệu về vấn đề này."
            else:
                final_answer = self.generator.generate(query, final_context)

        # ── Cache Write ───────────────────────────────────────────────────────────
        if not IS_EVAL_MODE and final_context and analysis.intent != "general":
            self.cache.add(query, query_embedding, final_answer)

        # ── Memory ────────────────────────────────────────────────────────────────
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