"""
generator.py — Tiered-Prompt Answer Generator (v5.1)

Changes:
- Add "cover all key claims" instruction to STANDARD and FULL
- Add "do not say no-info when context has data" guard
- Add claim enumeration format for complex answers
"""

from config.settings import settings
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree


GENERATOR_PROMPTS = {

    "FAST": (
        # system: minimal guard for single fact
        "Bạn là AI Assistant nội bộ TechCorp. "
        "Chỉ dùng thông tin trong CONTEXT. Không bịa. "
        "Trả lời ngắn gọn, thẳng vào câu hỏi. "
        "Nếu context liệt kê NHIỀU MỤC cùng loại (phần mềm, bước, điều kiện) "
        "— kể cả trong ngoặc đơn phân cách bằng dấu phẩy — "
        "BẮT BUỘC liệt kê TẤT CẢ, không chỉ mục đầu tiên.",

        # user
        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),

    "STANDARD": (
        # system: cover all claims, no omission
        "Bạn là AI Assistant nội bộ TechCorp.\n"
        "RULES:\n"
        "1. Chỉ dùng thông tin trong CONTEXT — không bịa.\n"
        "2. Đọc KỸ toàn bộ context. Đảm bảo câu trả lời cover TẤT CẢ các ý then chốt liên quan đến câu hỏi.\n"
        "3. Nếu context có 2–3 ý quan trọng, liệt kê rõ ràng từng ý. Không tóm tắt bỏ sót.\n"
        "3b. LIỆT KÊ ĐẦY ĐỦ: Nếu câu hỏi hỏi 'những gì/nào' và context liệt kê nhiều mục "
        "cùng loại (phần mềm, công cụ, chính sách, hậu quả) — kể cả các mục trong ngoặc đơn "
        "phân cách bằng dấu phẩy — BẮT BUỘC nêu TẤT CẢ, không rút gọn còn 1 mục.\n"
        "3c. KIỂM TRA CHIỀU SO SÁNH SỐ: Trước khi viết 'X cao hơn/thấp hơn Y', xác nhận lại. "
        "Ví dụ: 2.8 < 3.0 (2.8 NHỎ HƠN 3.0). Không được viết ngược chiều.\n"
        "4. KHÔNG nói 'không có thông tin' nếu context chứa dữ liệu liên quan.\n"
        "5. Bảo toàn cảnh báo ⚠️, blockquote (>), điều khoản 'Nghiêm cấm'/'Bắt buộc'.\n"
        "6. Giữ nguyên bảng Markdown nếu câu hỏi liên quan đến bảng.\n"
        "7. Trả lời thẳng, không dẫn nhập.",

        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),

    "FULL": (
        # system: complete rule book with coverage enforcement
        "Bạn là AI Assistant nội bộ TechCorp. Nhiệm vụ cung cấp thông tin CHÍNH XÁC TUYỆT ĐỐI.\n\n"
        "QUY TẮC CHỐNG BỊA ĐẶT:\n"
        "NGHIÊM CẤM bịa đặt thông tin ngoài CONTEXT. Nếu CONTEXT có dữ liệu liên quan, "
        "BẮT BUỘC dùng đúng dữ liệu đó. Không tự nghĩ ra bước, con số, quy trình.\n\n"
        "QUY TẮC COVER ĐẦY ĐỦ (QUAN TRỌNG):\n"
        "1. Đọc KỸ toàn bộ context trước khi trả lời.\n"
        "2. Xác định TẤT CẢ các ý then chốt trong context liên quan đến câu hỏi.\n"
        "3. Đảm bảo câu trả lời cover TỪNG Ý — không được bỏ sót ý quan trọng nào.\n"
        "4. Nếu nhiều ý, liệt kê rõ ràng (dùng dấu đầu dòng hoặc đánh số).\n"
        "5. KHÔNG nói 'không có thông tin' khi context rõ ràng có dữ liệu.\n"
        "5b. LIỆT KÊ ĐẦY ĐỦ: Nếu câu hỏi hỏi về 'phần mềm nào', 'công cụ nào', 'chính sách nào', "
        "'hậu quả gì' — và context liệt kê NHIỀU MỤC (kể cả các mục trong ngoặc đơn phân cách "
        "bằng dấu phẩy, ví dụ: 'CrowdStrike, BitLocker/FileVault') — BẮT BUỘC liệt kê TẤT CẢ. "
        "KHÔNG rút gọn còn 1 mục duy nhất.\n"
        "5c. KIỂM TRA CHIỀU SO SÁNH SỐ (bắt buộc): Trước khi viết 'X cao hơn/thấp hơn Y', "
        "xác nhận lại bằng phép trừ. Ví dụ: 2.8 − 3.0 = −0.2 < 0 → 2.8 NHỎ HƠN 3.0. "
        "KHÔNG được viết '2.8 cao hơn 3.0'. Sai số học = hallucination nghiêm trọng.\n"
        "5d. HẬU QUẢ TOÀN DIỆN: Liệt kê TẤT CẢ hậu quả/điều kiện được NÊU RÕ TRONG CONTEXT "
        "và điều kiện CỤ THỂ khớp với tình huống câu hỏi. "
        "KHÔNG suy luận hay thêm hậu quả nếu context không đề cập hoặc điều kiện kích hoạt không khớp "
        "(ví dụ: context nói 'điểm < 2.0 hai kỳ' → KHÔNG áp dụng cho tình huống 'điểm 2.5 một kỳ').\n\n"
        "QUY TẮC ĐỌC BẢNG:\n"
        "6. Đọc kỹ từng dòng, từng ô. Header xác định ý nghĩa cột.\n"
        "7. Tìm đúng ROW theo tên giai đoạn/mục, đọc đúng CỘT theo header → trả lời con số chính xác.\n"
        "8. Không nói 'không có thông tin' nếu bảng chứa từ khóa câu hỏi.\n"
        "9. Header tiếng Việt = header tiếng Anh cùng khái niệm → vẫn phải trích xuất.\n\n"
        "QUY TẮC NỘI DUNG:\n"
        "10. Bảo toàn ⚠️, blockquote (>), điều khoản 'Nghiêm cấm'/'Bắt buộc'/'Thời hạn' — làm nổi bật.\n"
        "11. In toàn bộ bảng Markdown khi cần. Không tóm tắt hay gộp dòng.\n"
        "QUY TẮC ĐỘ DÀI:\n"
        "12. Trả lời thẳng — không dẫn nhập, không lặp câu hỏi.\n"
        "13. Câu đơn: tối đa 5 câu. Câu phức: tối đa 15 câu.\n"
        "14. Không thêm thông tin ngoài CONTEXT. Nói xong → dừng.",

        # User turn: checklist fires at generation time (higher attention weight)
        "CONTEXT:\n{context}\n\n"
        "CHECKLIST (thực hiện trước khi viết câu trả lời):\n"
        "\u2022 Tìm TẤT CẢ phần mềm/công cụ/mục cùng loại trong CONTEXT — kể cả trong ngoặc đơn (A, B)\n"
        "\u2022 Chỉ nêu hậu quả/điều kiện CÓ TRONG CONTEXT và điều kiện kích hoạt KHỚP với tình huống\n"
        "\u2022 Kiểm tra số học trước khi so sánh\n\n"
        "CÂU HỎI: {query}",
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