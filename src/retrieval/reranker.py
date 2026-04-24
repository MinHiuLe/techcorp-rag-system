from src.schemas import QueryAnalysis
from config.settings import settings
from langsmith import traceable


class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker = rerank_client
        self.is_eval_mode = settings.EVAL_MODE

    def _get_policy(self, analysis: QueryAnalysis) -> tuple[int, float]:
        """
        Trả về (max_chunks, threshold) dựa trên độ phức tạp của câu hỏi.

        Complexity tiers:
          < 0.3  → Câu đơn giản (1 fact) → 2 chunks, threshold cao
          < 0.65 → Câu trung bình        → 3 chunks, threshold vừa
          >= 0.65→ Câu phức tạp/tổng hợp → 4 chunks, threshold thấp hơn

        Eval mode tăng threshold thêm 0.05 để chấm điểm chặt hơn.
        """
        complexity = analysis.complexity_score

        if complexity < 0.3:
            max_chunks, base_threshold = 2, 0.60
        elif complexity < 0.65:
            max_chunks, base_threshold = 3, 0.55
        else:
            max_chunks, base_threshold = 4, 0.50

        # Eval mode dùng threshold cao hơn một chút để precision chặt hơn
        threshold = base_threshold + 0.05 if self.is_eval_mode else base_threshold

        return max_chunks, threshold

    @traceable(run_type="tool", name="Cohere_Adaptive_Reranker")
    def apply_policy(self, query: str, documents: list, analysis: QueryAnalysis) -> list:
        if not documents:
            return []

        max_chunks, threshold = self._get_policy(analysis)

        # Đưa top 15 vào reranker, yêu cầu trả về top (max_chunks + 1) để có buffer lọc
        docs_to_rerank = documents[:15]
        docs_str = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rerank]

        reranked = self.reranker.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs_str,
            top_n=max_chunks + 1,  # Buffer: lấy thêm 1 để threshold filter có đủ ứng viên
        )

        final_context = []
        for r in reranked.results:
            if r.relevance_score >= threshold:
                final_context.append(docs_to_rerank[r.index])

            if len(final_context) >= max_chunks:
                break

            # Đảm bảo luôn có ít nhất 1 chunk nếu reranker quá chặt
            if not final_context:
                final_context.append(docs_to_rerank[reranked.results[0].index])

        print(
            f"  [Policy] Complexity={analysis.complexity_score:.2f} → "
            f"max_chunks={max_chunks}, threshold={threshold:.2f} → "
            f"Giữ lại {len(final_context)} chunks."
        )
        return final_context