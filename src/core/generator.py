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
        "4. Nếu ngữ cảnh KHÔNG TRỰC TIẾP trả lời câu hỏi, BẮT BUỘC nói 'Tôi không tìm thấy thông tin cụ thể về [chủ đề]'. Không suy diễn.\n"
        "5. Bảo toàn cảnh báo ⚠️, blockquote (>), điều khoản 'Nghiêm cấm'/'Bắt buộc'.\n"
        "6. Giữ nguyên bảng Markdown nếu câu hỏi liên quan đến bảng.\n"
        "7. Trả lời thẳng, không dẫn nhập.",

        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),

    "FULL": (
        # system: complete rule book with coverage enforcement
        "Bạn là AI Assistant nội bộ TechCorp. Nhiệm vụ cung cấp thông tin CHÍNH XÁC TUYỆT ĐỐI.\n\n"
        "QUY TẮC CHỐNG BỊA ĐẶT:\n"
        "NGHIÊM CẤM bịa đặt thông tin ngoài CONTEXT. Nếu CONTEXT không chứa thông tin TRỰC TIẾP và CỤ THỂ về chủ đề người dùng hỏi (ví dụ: hỏi về 'dự án ERP ngành y tế' nhưng context chỉ có 'kịch bản sales chung'), BẮT BUỘC phải trả lời: 'Tôi không tìm thấy thông tin cụ thể về [Chủ đề] trong tài liệu hiện tại'. KHÔNG suy diễn hoặc ép buộc dùng dữ liệu không liên quan.\n\n"
        "QUY TẮC COVER ĐẦY ĐỦ (QUAN TRỌNG):\n"
        "1. Đọc KỸ toàn bộ context trước khi trả lời.\n"
        "2. Xác định TẤT CẢ các ý then chốt trong context liên quan đến câu hỏi.\n"
        "3. Đảm bảo câu trả lời cover TỪNG Ý — không được bỏ sót ý quan trọng nào.\n"
        "4. Nếu nhiều ý, liệt kê rõ ràng (dùng dấu đầu dòng hoặc đánh số).\n"
        "5. CHỈ dùng dữ liệu từ context khi nó THỰC SỰ TRỰC TIẾP giải quyết được câu hỏi.\n"
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

    "GENERAL": (
        "Bạn là AI Assistant nội bộ TechCorp. Hãy trả lời các câu hỏi giao tiếp thông thường, "
        "hoặc kiến thức cơ bản (chào hỏi, ngày tháng, tính toán cơ bản) một cách thân thiện, ngắn gọn. "
        "Tuyệt đối không bịa đặt các thông tin, quy trình, chính sách nội bộ TechCorp. "
        "Nếu người dùng hỏi về công việc, hãy hướng dẫn họ đặt câu hỏi cụ thể.",
        
        "CÂU HỎI: {query}"
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
                "ls_provider": "groq",
                "ls_model_name": settings.LLM_MODEL,
                "ls_prompt_tokens":      response.usage.prompt_tokens,
                "ls_completion_tokens":  response.usage.completion_tokens,
                "ls_total_tokens":       response.usage.total_tokens,
                "complexity":         complexity,
                "prompt_tier":        prompt_tier,
                "max_output_tokens":  max_output_tokens,
            })

        return response.choices[0].message.content

    @traceable(run_type="llm", name="Groq_Llama3_Stream_Generator")
    def stream_generate(
        self,
        original_query: str,
        context: str,
        complexity: float = 0.5,
        prompt_tier: str = "FULL",
        max_output_tokens: int = 500,
    ):
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
            stream=True,
        )

        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
                
            # Log token usage nếu có (thường nằm ở chunk cuối cùng khi stream kết thúc)
            usage_data = None
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_data = chunk.usage
            elif hasattr(chunk, 'x_groq') and chunk.x_groq and hasattr(chunk.x_groq, 'usage'):
                usage_data = chunk.x_groq.usage
                
            if usage_data:
                import logging
                logging.getLogger(__name__).info(f"[Token Tracker] Tìm thấy usage: {usage_data}")
                rt = get_current_run_tree()
                if rt:
                    # Gán trực tiếp vào outputs (LangSmith thường tìm token trong outputs.usage hoặc metadata)
                    prompt_tokens = getattr(usage_data, "prompt_tokens", 0)
                    completion_tokens = getattr(usage_data, "completion_tokens", 0)
                    total_tokens = getattr(usage_data, "total_tokens", 0)
                    
                    # Cập nhật metadata chuẩn của LangSmith
                    rt.add_metadata({
                        "ls_provider": "groq",
                        "ls_model_name": settings.LLM_MODEL,
                        "ls_prompt_tokens": prompt_tokens,
                        "ls_completion_tokens": completion_tokens,
                        "ls_total_tokens": total_tokens,
                    })
                    
                    # Dự phòng: thêm vào tags
                    rt.add_tags([f"Tokens: {total_tokens}"])