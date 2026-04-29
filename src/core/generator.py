from config.settings import settings
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree


class Generator:
    def __init__(self, llm_client):
        self.llm = llm_client

    def _get_token_budget(self, complexity: float) -> int:
        """
        Map complexity_score → max_tokens budget.

        - < 0.3  : câu hỏi đơn giản, 1 fact → 300 tokens là dư
        - < 0.65 : câu hỏi trung bình, vài điểm cần trình bày → 500 tokens
        - >= 0.65: câu hỏi phức tạp, multi-topic hoặc cần liệt kê nhiều → 800 tokens

        Ceiling 800 đủ cho mọi câu trả lời Q&A nội bộ mà không gây over-generation.
        """
        if complexity < 0.3:
            return 400
        elif complexity < 0.65:
            return 500
        else:
            return 800

    @traceable(run_type="llm", name="Groq_Llama3_Generator")
    def generate(self, original_query: str, context: str, complexity: float = 0.5) -> str:
        token_budget = self._get_token_budget(complexity)

        prompt = f"""
Bạn là AI Assistant nội bộ của TechCorp. Nhiệm vụ của bạn là cung cấp thông tin dựa trên tài liệu được cung cấp một cách CHÍNH XÁC TUYỆT ĐỐI.

QUY TẮC NỘI DUNG (PHẢI TUÂN THỦ):
1. BẢO TOÀN CẢNH BÁO VÀ QUY TẮC: TUYỆT ĐỐI KHÔNG bỏ sót các cảnh báo (⚠️), ghi chú, blockquote (>), hoặc các điều khoản "Nghiêm cấm", "Bắt buộc", "Thời hạn" (VD: 24h). Phải làm nổi bật chúng trong câu trả lời.
2. BẢO TOÀN ĐỊNH DẠNG BẢNG: Nếu tài liệu chứa bảng biểu (Markdown table), bạn PHẢI in ra toàn bộ bảng đó bằng định dạng Markdown chuẩn. Không được tóm tắt, tự ý gộp dòng hay làm vỡ cấu trúc bảng.
3. NGUỒN: Nếu có câu trả lời, BẮT BUỘC ghi nguồn ở dòng riêng theo format "Nguồn: tên_file", không được ghi inline trong câu trả lời.

QUY TẮC ĐỘ DÀI (PHẢI TUÂN THỦ):
4. Trả lời TRỰC TIẾP vào câu hỏi, KHÔNG dẫn nhập, KHÔNG lặp lại câu hỏi.
5. Câu hỏi đơn giản (1 thông tin): tối đa 3–5 câu. Câu hỏi phức tạp: tối đa 10–15 câu.
6. KHÔNG thêm "Tuy nhiên", "Lưu ý thêm", "Ngoài ra" nếu thông tin đó KHÔNG có trong tài liệu gốc.
7. KHÔNG tóm tắt lại câu trả lời ở cuối. Nói xong → dừng.

CONTEXT CỦA HỆ THỐNG:
{context}

CÂU HỎI CỦA NGƯỜI DÙNG:
{original_query}
"""
        response = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=token_budget,
        )

        run = get_current_run_tree()
        if run and hasattr(response, 'usage') and response.usage:
            run.add_metadata({
                "prompt_tokens":      response.usage.prompt_tokens,
                "completion_tokens":  response.usage.completion_tokens,
                "total_tokens":       response.usage.total_tokens,
                "complexity":         complexity,
                "token_budget":       token_budget,
            })

        return response.choices[0].message.content