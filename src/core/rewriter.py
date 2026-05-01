from src.schemas import QueryAnalysis
from config.settings import settings


class QueryRewriter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def _has_entity_mismatch(self, query: str, entities: list[str]) -> bool:
       
        if not entities:
            return False
        query_lower = query.lower()
        missing = sum(1 for e in entities if e.lower() not in query_lower)
        return missing > len(entities) / 2

    def _is_over_rewritten(self, original: str, rewritten: str) -> bool:
      
        return len(rewritten) > len(original) * 2.5

    def rewrite(self, query: str, analysis: QueryAnalysis, history: str = "") -> str:
        """
        Chỉ rewrite khi thực sự cần:
        - complexity cao (>= 0.5, tăng từ 0.35) → câu phức tạp thật sự
        - ambiguity cao (>= 0.4, tăng từ 0.3) → câu thực sự mơ hồ
        - entity mismatch THỰC SỰ (hơn nửa entities thiếu, không phải 1 entity)
        """
        needs_rewrite = (
            analysis.complexity_score >= 0.58       
            or analysis.ambiguity_score >= 0.4     
            or self._has_entity_mismatch(query, analysis.entities)
        )
        if not needs_rewrite:
            return query

        prompt = f"""Viết lại CÂU HỎI HIỆN TẠI để tối ưu cho Vector Search trong hệ thống nội bộ TechCorp.

NGUYÊN TẮC BẮT BUỘC:
- GIỮ NGUYÊN mọi thuật ngữ kỹ thuật, tên sản phẩm, tên quy trình đã có trong câu hỏi gốc.
  VD: "Weighted pipeline", "Docker image tag", "AD account" → KHÔNG được đổi hoặc giải thích.
- NẾU có đại từ mơ hồ ("nó", "cái đó", "vấn đề này"), đọc LỊCH SỬ để thay bằng danh từ gốc.
- NẾU query dùng từ thông dụng thay cho thuật ngữ chính xác (VD: "lấy" → "cấp phát"),
  hãy dùng thuật ngữ kỹ thuật. Entities gợi ý: {analysis.entities}
- Câu rewrite phải NGẮN HƠN hoặc TƯƠNG ĐƯƠNG độ dài câu gốc, không được dài hơn.
- Chỉ trả về duy nhất chuỗi văn bản đã rewrite, không giải thích thêm.

LỊCH SỬ HỘI THOẠI GẦN ĐÂY:
{history}

CÂU HỎI HIỆN TẠI: {query}"""

        response = self.llm.chat.completions.create(
            model=settings.UTILITY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,    
        )
        rewritten = response.choices[0].message.content.strip()

     
        if self._is_over_rewritten(query, rewritten):
            print(f"  [Rewriter] '{query}' → SKIP (over-rewritten, fallback to original)")
            return query

        print(f"  [Rewriter] '{query}' → '{rewritten}'")
        return rewritten