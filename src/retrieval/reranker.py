from src.schemas import QueryAnalysis
from config.settings import settings
from langsmith import traceable
class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker = rerank_client
        self.is_eval_mode = settings.EVAL_MODE

    @traceable(run_type="tool", name="Cohere_Adaptive_Reranker")
    def apply_policy(self, query: str, documents: list, analysis: QueryAnalysis) -> list:
        if not documents: return []

        # Đưa top 15 vào reranker
        docs_to_rerank = documents[:15]
        docs_str = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rerank]
        
        reranked = self.reranker.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs_str,
            top_n=5
        )

        final_context = []
        threshold = 0.50 if self.is_eval_mode else 0.40

        for r in reranked.results:
            if r.relevance_score >= threshold:
                final_context.append(docs_to_rerank[r.index])
            
            # Max context chunks: 4 (Hard stop)
            if len(final_context) >= 4:
                break

        print(f"  [Policy] Lọc Reranker: Giữ lại {len(final_context)} chunks (Score >= {threshold}).")
        return final_context