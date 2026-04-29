from src.schemas import QueryAnalysis
from config.settings import settings
from langsmith import traceable


class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker     = rerank_client
        self.is_eval_mode = settings.EVAL_MODE

    def _get_top_k(self, analysis: QueryAnalysis, n_topics: int = 1) -> int:
        """
        Adaptive top_k dựa trên complexity VÀ số lượng topic.

        Trước đây:
          complexity < 0.65 → top_k=3  ← quá thấp cho multi-topic query
          complexity >= 0.65 → top_k=4

        Sau fix:
          Mỗi topic cần ít nhất 2 chunks để có đủ context.
          top_k = base_k × n_topics, cap tại 8 để tránh context quá dài.

        VD: Docker + VPN (2 topics, complexity=0.8)
          base_k = 3, n_topics = 2 → top_k = min(6, 8) = 6
          → mỗi topic có ~3 chunks thay vì tranh nhau 3 chunks
        """
        complexity = analysis.complexity_score

        if complexity < 0.3:
            base_k = 2
        elif complexity < 0.65:
            base_k = 3
        else:
            base_k = 4

        top_k = min(base_k * n_topics, 8)  # cap tại 8
        return top_k

    @traceable(run_type="tool", name="Cohere_Adaptive_Reranker")
    def apply_policy(
        self,
        query: str,
        documents: list,
        analysis: QueryAnalysis,
        n_topics: int = 1,
    ) -> list:
        if not documents:
            return []

        top_k        = self._get_top_k(analysis, n_topics)
        docs_to_rank = documents[:15]  
        docs_str     = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rank]

        reranked = self.reranker.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs_str,
            top_n=top_k,
        )

        final_docs = [docs_to_rank[r.index] for r in reranked.results]

        if not final_docs and documents:
            final_docs = [documents[0]]

        print(
            f"  [Policy] complexity={analysis.complexity_score:.2f} "
            f"n_topics={n_topics} → top_k={top_k} "
            f"→ Giữ lại {len(final_docs)} chunks."
        )
        return final_docs