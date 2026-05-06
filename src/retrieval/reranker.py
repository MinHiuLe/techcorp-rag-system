import logging
from src.schemas import QueryAnalysis
from config.settings import settings
from langsmith import traceable

logger = logging.getLogger(__name__)


class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker = rerank_client
        self.is_eval_mode = settings.EVAL_MODE

    def _get_top_k(self, analysis: QueryAnalysis, n_topics: int = 1) -> int:
        complexity = analysis.complexity_score

        if complexity < 0.3:
            base_k = 2
        elif complexity < 0.65:
            base_k = 3
        else:
            base_k = 4

        return min(base_k * n_topics, 8)

    def _balance_by_source(self, ranked_docs, top_k, n_topics):
        if n_topics <= 1:
            return ranked_docs[:top_k]

        by_source = {}
        for doc in ranked_docs:
            by_source.setdefault(doc["source"], []).append(doc)

        if len(by_source) <= 1:
            return ranked_docs[:top_k]

        min_per_source = max(1, min(2, top_k // len(by_source)))

        balanced = []
        used_texts = set()

        for docs in by_source.values():
            for doc in docs[:min_per_source]:
                if doc["text"] not in used_texts:
                    balanced.append(doc)
                    used_texts.add(doc["text"])

        for doc in ranked_docs:
            if len(balanced) >= top_k:
                break
            if doc["text"] not in used_texts:
                balanced.append(doc)
                used_texts.add(doc["text"])

        return balanced

    @traceable(run_type="tool", name="Cohere_Adaptive_Reranker")
    def apply_policy(
        self,
        query: str,
        documents: list,
        analysis: QueryAnalysis,
        n_topics: int = 1,
        top_k_override: int | None = None,
    ) -> list:
        if not documents:
            return []

        top_k = top_k_override or self._get_top_k(analysis, n_topics)
        docs_to_rank = documents[:15]
        docs_str = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rank]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                reranked = self.reranker.rerank(
                    model="rerank-multilingual-v3.0",
                    query=query,
                    documents=docs_str,
                    top_n=top_k,
                )
                break
            except Exception as e:
                err_str = str(e).lower()
                if ("429" in err_str or "rate limit" in err_str or "too many requests" in err_str) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 15 # Cohere trial cần thời gian nghỉ lâu hơn
                    logger.warning(f"⚠️  Cohere Rate Limit (429). Thử lại sau {wait_time}s... (Lần {attempt+1})")
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"❌ Lỗi Cohere Rerank: {e}")
                    # Fallback về top_k ban đầu nếu lỗi hoàn toàn
                    return documents[:top_k]

        ranked_docs = [docs_to_rank[r.index] for r in reranked.results]

        if not ranked_docs:
            ranked_docs = documents[:top_k]

        return self._balance_by_source(ranked_docs, top_k, n_topics)