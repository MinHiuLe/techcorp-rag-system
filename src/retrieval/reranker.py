from src.schemas import QueryAnalysis
from config.settings import settings
from langsmith import traceable
 
 
class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker = rerank_client
        self.is_eval_mode = settings.EVAL_MODE
 
    def _get_top_k(self, analysis: QueryAnalysis) -> int:
        """
        Chỉ quyết định số chunk giữ lại, không dùng threshold.
        LLM là tầng lọc cuối — reranker chỉ có nhiệm vụ sắp xếp.
        """
        complexity = analysis.complexity_score
        if complexity < 0.3:
            return 2
        elif complexity < 0.65:
            return 3
        else:
            return 4
 
    @traceable(run_type="tool", name="Cohere_Adaptive_Reranker")
    def apply_policy(self, query: str, documents: list, analysis: QueryAnalysis) -> list:
        if not documents:
            return []
 
        top_k = self._get_top_k(analysis)
        docs_to_rerank = documents[:15]
        docs_str = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rerank]
 
 
        reranked = self.reranker.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs_str,
            top_n=top_k, 
        )
 
        final_context = [docs_to_rerank[r.index] for r in reranked.results]

        if not final_context and documents:
            final_context = [documents[0]]
 
        print(
            f"  [Policy] Complexity={analysis.complexity_score:.2f} → "
            f"top_k={top_k} → Giữ lại {len(final_context)} chunks."
        )
        return final_context