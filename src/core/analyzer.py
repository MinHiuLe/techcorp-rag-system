import json
from pydantic import ValidationError
from src.schemas import QueryAnalysis
from config.settings import settings


class QueryAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client

    def analyze(self, query: str, history: str = "") -> QueryAnalysis:
        # Chỉ đưa history vào prompt khi thực sự có nội dung
        history_section = (
            f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{history}\n"
            if history and history != "Không có."
            else ""
        )

        prompt = f"""Phân tích câu hỏi HIỆN TẠI và trả về JSON với 4 trường sau:

1. "intent": "technical" (tra cứu IT/HR/Sales/nghiệp vụ) hoặc "general" (chỉ dành cho chào hỏi thuần túy).
2. "complexity_score": float 0.0–1.0.
   - 0.0–0.3: câu hỏi đơn giản, 1 fact, 1 tài liệu.
   - 0.3–0.65: câu hỏi vừa, cần 1–2 tài liệu.
   - 0.65–1.0: câu hỏi phức tạp, cần tổng hợp nhiều tài liệu hoặc có nhiều câu hỏi con.
3. "ambiguity_score": float 0.0–1.0. Cao khi dùng đại từ ("nó", "cái đó") hoặc thiếu context.
4. "entities": mảng string — các từ khóa kỹ thuật quan trọng. Nếu dùng đại từ, lấy entity từ lịch sử.

LƯU Ý QUAN TRỌNG:
- Nếu câu hỏi chứa NHIỀU DẤU "?" hoặc hỏi về NHIỀU CHỦ ĐỀ KHÁC NHAU (VD: Docker + VPN, nghỉ phép + lương),
  hãy đặt complexity_score >= 0.8 để hệ thống biết cần xử lý multi-topic.
- Câu KHÔNG có dấu "?" là câu kể / trình bày tình huống (VD: "mình bị công ty đánh giá...", "máy tôi bị lỗi...").
  Đây là câu ĐƠN CHỦ ĐỀ → complexity_score KHÔNG được vượt quá 0.65, bất kể nội dung.
- Chỉ trả về JSON, không giải thích thêm.

{history_section}CÂU HỎI HIỆN TẠI: {query}"""

        response = self.llm.chat.completions.create(
            model=settings.UTILITY_MODEL,  # 8B đủ cho classification task
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,              # FIX: 0.1 → 0.0 để deterministic
            response_format={"type": "json_object"},
        )
        try:
            return QueryAnalysis(**json.loads(response.choices[0].message.content))
        except (ValidationError, Exception):
            return QueryAnalysis(
                intent="technical",
                complexity_score=0.5,
                ambiguity_score=0.5,
                entities=[],
            )