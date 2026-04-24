from config.settings import settings
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

class Generator:
    def __init__(self, llm_client):
        self.llm = llm_client

    @traceable(run_type="llm", name="Groq_Llama3_Generator")
    def generate(self, original_query: str, context: str) -> str:
        prompt = f"""
Bạn là AI Assistant nội bộ của TechCorp. Nhiệm vụ của bạn là cung cấp thông tin dựa trên tài liệu được cung cấp một cách CHÍNH XÁC TUYỆT ĐỐI.

QUY TẮC NGHIÊM NGẶT (PHẢI TUÂN THỦ):
1. BẢO TOÀN CẢNH BÁO VÀ QUY TẮC: TUYỆT ĐỐI KHÔNG bỏ sót các cảnh báo (⚠️), ghi chú, blockquote (>), hoặc các điều khoản "Nghiêm cấm", "Bắt buộc", "Thời hạn" (VD: 24h). Phải làm nổi bật chúng trong câu trả lời.
2. BẢO TOÀN ĐỊNH DẠNG BẢNG: Nếu tài liệu chứa bảng biểu (Markdown table), bạn PHẢI in ra toàn bộ bảng đó bằng định dạng Markdown chuẩn. Không được tóm tắt, tự ý gộp dòng hay làm vỡ cấu trúc bảng.
3. CHỈ DÙNG DỮ LIỆU ĐƯỢC CẤP: Không tự bịa thêm thông tin. Nếu Context không chứa câu trả lời, chỉ cần nói "Hệ thống chưa có tài liệu về vấn đề này." và KHÔNG trích dẫn nguồn.
4. NGUỒN: Nếu có câu trả lời, BẮT BUỘC ghi [Nguồn: tên_file] ở cuối.

CONTEXT CỦA HỆ THỐNG:
{context}

CÂU HỎI CỦA NGƯỜI DÙNG:
{original_query}
"""
        response = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0, 
            max_tokens=2048, 
        )

        run = get_current_run_tree()
        if run and hasattr(response, 'usage') and response.usage:
            run.add_metadata({
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            })

        return response.choices[0].message.content