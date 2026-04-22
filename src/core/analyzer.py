import json
from pydantic import ValidationError
from src.schemas import QueryAnalysis
from config.settings import settings

class QueryAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client

    def analyze(self, query: str, history: str = "") -> QueryAnalysis:
        prompt = f"""
Phân tích câu hỏi HIỆN TẠI của người dùng dựa trên LỊCH SỬ HỘI THOẠI (nếu có) và trả về JSON:
1. Intent: 'technical' (Tra cứu IT, nghiệp vụ, nhân sự) hoặc 'general' (CHỈ DÀNH CHO chào hỏi).
2. Complexity Score: 0.0 (rất dễ, 1 fact) -> 1.0 (rất khó, cần so sánh/tổng hợp).
3. Ambiguity Score: 0.0 (rõ ràng) -> 1.0 (mập mờ, dùng đại từ thay thế).
4. Entities: Mảng từ khóa kỹ thuật. NẾU dùng đại từ, hãy trích xuất Entity từ LỊCH SỬ.

LỊCH SỬ HỘI THOẠI GẦN ĐÂY:
{history}

CÂU HỎI HIỆN TẠI: {query}
"""
        response = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        try:
            return QueryAnalysis(**json.loads(response.choices[0].message.content))
        except ValidationError:
            return QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.5, entities=[])