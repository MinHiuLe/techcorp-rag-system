from src.schemas import QueryAnalysis
from config.settings import settings
from langsmith import traceable


class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker     = rerank_client
        self.is_eval_mode = settings.EVAL_MODE

    def _get_top_k(self, analysis: QueryAnalysis, n_topics: int = 1) -> int:
        complexity = analysis.complexity_score

        if complexity < 0.3:
            base_k = 2
        elif complexity < 0.65:
            base_k = 3
        else:
            base_k = 4

        top_k = min(base_k * n_topics, 8)  # cap tại 8
        return top_k

    def _balance_by_source(
        self,
        ranked_docs: list,
        top_k: int,
        n_topics: int,
    ) -> list:

        if n_topics <= 1:
            return ranked_docs[:top_k]

        # Group by source, giữ nguyên Cohere rank order trong từng group
        by_source: dict[str, list] = {}
        for doc in ranked_docs:
            by_source.setdefault(doc["source"], []).append(doc)

        n_sources = len(by_source)
        if n_sources <= 1:
            # Tất cả cùng 1 file → không cần balance
            return ranked_docs[:top_k]

        # min_per_source: 2 nếu budget đủ, fallback 1
        min_per_source = max(1, min(2, top_k // n_sources))

        balanced   = []
        used_texts = set()

        # Pass 1: guaranteed slots — 2 chunks tốt nhất từ mỗi source
        for docs in by_source.values():
            for doc in docs[:min_per_source]:
                if doc["text"] not in used_texts:
                    balanced.append(doc)
                    used_texts.add(doc["text"])

        # Pass 2: fill remaining slots theo Cohere rank order
        for doc in ranked_docs:
            if len(balanced) >= top_k:
                break
            if doc["text"] not in used_texts:
                balanced.append(doc)
                used_texts.add(doc["text"])

        sources_in_result = {d["source"] for d in balanced}
        print(
            f"  [Balance] {n_sources} nguồn → "
            f"{len(balanced)} chunks từ {len(sources_in_result)} file: "
            f"{', '.join(sources_in_result)}"
        )
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

        top_k = top_k_override if top_k_override is not None else self._get_top_k(analysis, n_topics)
        docs_to_rank = documents[:15]
        docs_str     = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rank]

        reranked = self.reranker.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs_str,
            top_n=top_k,
        )

        ranked_docs = [docs_to_rank[r.index] for r in reranked.results]

        if not ranked_docs and documents:
            ranked_docs = documents[:top_k]

        final_docs = self._balance_by_source(ranked_docs, top_k, n_topics)

        print(
            f"  [Policy] complexity={analysis.complexity_score:.2f} "
            f"n_topics={n_topics} → top_k={top_k} "
            f"→ Giữ lại {len(final_docs)} chunks."
        )
        return final_docs