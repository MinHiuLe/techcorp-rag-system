from src.schemas import QueryAnalysis
from config.settings import settings
 
 
class QueryRewriter:
    def __init__(self, llm_client):
        self.llm = llm_client
 
    def _has_entity_mismatch(self, query: str, entities: list[str]) -> bool:
        """
        True nếu có entity nào không xuất hiện lexically trong query gốc.
        VD: query="lấy laptop mới", entities=["cấp phát thiết bị"] → True → cần rewrite.
        """
        query_lower = query.lower()
        return any(e.lower() not in query_lower for e in entities)
 
    def rewrite(self, query: str, analysis: QueryAnalysis, history: str = "") -> str:
        # Rewrite nếu: ambiguous, phức tạp, HOẶC entity không khớp lexically
        needs_rewrite = (
            analysis.complexity_score >= 0.35
            or analysis.ambiguity_score >= 0.3
            or self._has_entity_mismatch(query, analysis.entities)
        )
        if not needs_rewrite:
            return query
 
        prompt = f"""
Viết lại CÂU HỎI HIỆN TẠI để tối ưu cho Vector Search.
- NẾU câu hỏi dùng từ thay thế hoặc từ thông dụng (VD: "lấy" thay cho "cấp phát"), hãy dùng thuật ngữ kỹ thuật chính xác.
- NẾU câu hỏi dùng đại từ, hãy ĐỌC LỊCH SỬ để thay bằng danh từ gốc.
- Bổ sung các Entities sau vào câu: {analysis.entities}
- Bỏ các từ giao tiếp thừa thãi. Chỉ trả về duy nhất chuỗi văn bản đã rewrite.
LỊCH SỬ HỘI THOẠI GẦN ĐÂY:
{history}
CÂU HỎI HIỆN TẠI: {query}
"""
        response = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        rewritten = response.choices[0].message.content.strip()
        print(f"  [Rewriter] '{query}' → '{rewritten}'")
        return rewritten