from src.schemas import QueryAnalysis
from config.settings import settings

class QueryRewriter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def rewrite(self, query: str, analysis: QueryAnalysis, history: str = "") -> str:
        if analysis.complexity_score < 0.2 and analysis.ambiguity_score < 0.3:
            return query

        prompt = f"""
Viết lại CÂU HỎI HIỆN TẠI để tối ưu cho Vector Search.
- NẾU câu hỏi dùng từ thay thế, hãy ĐỌC LỊCH SỬ để thay bằng danh từ gốc.
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
        return response.choices[0].message.content.strip()