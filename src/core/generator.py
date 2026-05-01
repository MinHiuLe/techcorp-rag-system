"""
generator.py — Tiered-Prompt Answer Generator

Token budget so sánh (trước → sau):
  FAST     : 433 → ~25  prompt tokens  (-408 tok/query)
  STANDARD : 433 → ~80  prompt tokens  (-353 tok/query)
  FULL     : 433 → 433  prompt tokens  (không đổi, vẫn cần bảo vệ đầy đủ)

Mỗi tier thêm đúng những guard rails cần thiết, không thừa không thiếu.
"""

from config.settings import settings
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree


# ── Tiered Prompt Library ─────────────────────────────────────────────────────
# Nguyên tắc thiết kế:
#   FAST     → chỉ 3 ràng buộc cốt lõi (không bịa, trả lời thẳng, ghi nguồn)
#   STANDARD → thêm bảo toàn cảnh báo (⚠️) và định dạng bảng
#   FULL     → toàn bộ rule book: đọc bảng chi tiết, cross-language header, etc.
#
# FAST và STANDARD dùng system/user split để token system prompt được cache
# phía Groq (prefix caching nếu model hỗ trợ); FULL vẫn single-turn vì
# nội dung context thay đổi mỗi lần.

GENERATOR_PROMPTS = {

    "FAST": (
        # system
        "Bạn là AI Assistant nội bộ TechCorp. "
        "Chỉ dùng thông tin trong CONTEXT. Không bịa. "
        "Trả lời ngắn gọn, thẳng vào câu hỏi.",  # ← dấu phẩy tách system / user

        # user template  (format: .format(context=..., query=...))
        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),

    "STANDARD": (
        # system
        "Bạn là AI Assistant nội bộ TechCorp.\n"
        "RULES:\n"
        "1. Chỉ dùng thông tin trong CONTEXT — không bịa.\n"
        "2. Bảo toàn cảnh báo ⚠️, blockquote (>), điều khoản 'Nghiêm cấm'/'Bắt buộc'.\n"
        "3. Giữ nguyên bảng Markdown nếu câu hỏi liên quan đến bảng.\n"
        "4. Trả lời thẳng, không dẫn nhập.",  # ← dấu phẩy tách system / user

        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),

    "FULL": (
        # system — toàn bộ rule book cho câu phức tạp / multi-topic / bảng dữ liệu
        "Bạn là AI Assistant nội bộ TechCorp. Nhiệm vụ cung cấp thông tin CHÍNH XÁC TUYỆT ĐỐI.\n\n"
        "QUY TẮC CHỐNG BỊA ĐẶT:\n"
        "NGHIÊM CẤM bịa đặt thông tin ngoài CONTEXT. Nếu CONTEXT có dữ liệu liên quan, "
        "BẮT BUỘC dùng đúng dữ liệu đó. Không tự nghĩ ra bước, con số, quy trình.\n\n"
        "QUY TẮC ĐỌC BẢNG:\n"
        "1. Đọc kỹ từng dòng, từng ô. Header xác định ý nghĩa cột.\n"
        "2. Tìm đúng ROW theo tên giai đoạn/mục, đọc đúng CỘT theo header → trả lời con số chính xác.\n"
        "3. Không nói 'không có thông tin' nếu bảng chứa từ khóa câu hỏi.\n"
        "4. Header tiếng Việt = header tiếng Anh cùng khái niệm → vẫn phải trích xuất.\n\n"
        "QUY TẮC NỘI DUNG:\n"
        "5. Bảo toàn ⚠️, blockquote (>), điều khoản 'Nghiêm cấm'/'Bắt buộc'/'Thời hạn' — làm nổi bật.\n"
        "6. In toàn bộ bảng Markdown khi cần. Không tóm tắt hay gộp dòng.\n"
        "QUY TẮC ĐỘ DÀI:\n"
        "8. Trả lời thẳng — không dẫn nhập, không lặp câu hỏi.\n"
        "9. Câu đơn: tối đa 5 câu. Câu phức: tối đa 15 câu.\n"
        "10. Không thêm thông tin ngoài CONTEXT. Nói xong → dừng.",

        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),
}


class Generator:
    def __init__(self, llm_client):
        self.llm = llm_client

    @traceable(run_type="llm", name="Groq_Llama3_Generator")
    def generate(
        self,
        original_query: str,
        context: str,
        complexity: float = 0.5,   
        prompt_tier: str = "FULL",  
        max_output_tokens: int = 500, 
    ) -> str:
        system_tmpl, user_tmpl = GENERATOR_PROMPTS[prompt_tier]
        user_content = user_tmpl.format(context=context, query=original_query)

        response = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_tmpl},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.0,
            max_tokens=max_output_tokens,
        )

        # ── LangSmith metadata ────────────────────────────────────────────────
        run = get_current_run_tree()
        if run and hasattr(response, "usage") and response.usage:
            run.add_metadata({
                "prompt_tokens":      response.usage.prompt_tokens,
                "completion_tokens":  response.usage.completion_tokens,
                "total_tokens":       response.usage.total_tokens,
                "complexity":         complexity,
                "prompt_tier":        prompt_tier,
                "max_output_tokens":  max_output_tokens,
            })

        return response.choices[0].message.content