"""
generator.py — Tiered-Prompt Answer Generator (v5.1)

Changes:
- Add "cover all key claims" instruction to STANDARD and FULL
- Add "do not say no-info when context has data" guard
- Add claim enumeration format for complex answers
"""

from config.settings import settings
# pyrefly: ignore [missing-import]
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree # pyright: ignore [reportMissingImports]
from langsmith import trace # pyrefly: ignore [missing-import]

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
        "6. BẢO TOÀN VÀ ƯU TIÊN BẢNG: BẮT BUỘC trình bày dạng BẢNG (Markdown table) cho mọi thông tin có tính chất liệt kê đối tượng kèm thuộc tính hoặc mô tả (ví dụ: Vai trò - Quyền hạn, Tên - Mô tả, Mốc thời gian - Hành động). Tuyệt đối không dùng danh sách gạch đầu dòng hay định dạng 'Tên: Mô tả'.\n"
        "   - Ví dụ: | Đối tượng | Mô tả/Quyền hạn |\n"
        "            | :--- | :--- |\n"
        "            | Developer | Có quyền Create/Update issue |\n"
        "6b. CÁCH LY NGUỒN: Nội dung từ các nguồn khác nhau phải ở các bảng/đoạn riêng.\n"
        "6c. TUYỆT ĐỐI KHÔNG DÙNG HTML: Cấm dùng <div>, <table>, <p>, <br>. Chỉ dùng Markdown chuẩn.\n"
        "7. VĂN PHONG TỰ NHIÊN: Không mở đầu bằng 'Dựa trên CONTEXT'. Trả lời thẳng vào vấn đề.",

        "CONTEXT:\n{context}\n\nCÂU HỎI: {query}",
    ),

    "FULL": (
        # system: complete rule book with coverage enforcement
        "Bạn là AI Assistant nội bộ TechCorp. Nhiệm vụ cung cấp thông tin CHÍNH XÁC TUYỆT ĐỐI.\n\n"
        "QUY TẮC CHỐNG BỊA ĐẶT:\n"
        "NGHIÊM CẤM bịa đặt thông tin ngoài CONTEXT. Nếu CONTEXT không chứa thông tin TRỰC TIẾP và CỤ THỂ về chủ đề người dùng hỏi, BẮT BUỘC phải trả lời: 'Tôi không tìm thấy thông tin cụ thể về [Chủ đề]'. KHÔNG suy diễn.\n\n"
        "QUY TẮC COVER ĐẦY ĐỦ (QUAN TRỌNG):\n"
        "1. Đọc KỸ toàn bộ context trước khi trả lời.\n"
        "2. Xác định TẤT CẢ các ý then chốt trong context liên quan đến câu hỏi.\n"
        "3. Đảm bảo câu trả lời cover TỪNG Ý — không được bỏ sót ý quan trọng nào.\n"
        "4. Nếu nhiều ý, ưu tiên dùng bảng.\n"
        "5. CHỈ dùng dữ liệu từ context khi nó THỰC SỰ TRỰC TIẾP giải quyết được câu hỏi.\n"
        "5b. LIỆT KÊ ĐẦY ĐỦ: BẮT BUỘC liệt kê TẤT CẢ các mục được nêu, không rút gọn.\n"
        "5c. KIỂM TRA CHIỀU SO SÁNH SỐ: Không được nhầm lẫn lớn hơn/nhỏ hơn.\n"
        "5d. HẬU QUẢ TOÀN DIỆN: Liệt kê TẤT CẢ hậu quả/điều kiện CÓ TRONG CONTEXT và KHỚP với tình huống.\n\n"
        "QUY TẮC ĐỌC VÀ TRÌNH BÀY BẢNG:\n"
        "6. Đọc kỹ từng dòng, từng ô. Header xác định ý nghĩa cột.\n"
        "7. Tối đa hóa việc dùng BẢNG (Markdown table) cho các câu hỏi liệt kê thuộc tính (ví dụ: các quyền, vai trò, thông số). NẾU TRONG CONTEXT CÓ BẢNG, PHẢI GIỮ NGUYÊN BẢNG.\n"
        "8. Không tóm tắt bảng thành dạng danh sách (bullet list).\n"
        "9. CÁCH LY NGUỒN: Thông tin từ các nguồn khác nhau phải ở các bảng/đoạn riêng biệt.\n"
        "9b. KHÔNG DÙNG THẺ HTML: TUYỆT ĐỐI KHÔNG dùng thẻ HTML (<div>, <table>) để định dạng. Bắt buộc dùng Markdown thuần túy.\n\n"
        "QUY TẮC VĂN PHONG:\n"
        "10. Bảo toàn ⚠️, blockquote (>), điều khoản 'Nghiêm cấm'.\n"
        "11. VĂN PHONG TỰ NHIÊN: Trả lời thẳng vào vấn đề. TUYỆT ĐỐI KHÔNG mở bài bằng các câu máy móc như 'Dựa trên CONTEXT, ...', 'Theo tài liệu, ...'.\n"
        "12. Không lặp lại câu hỏi. Nói xong → dừng.",

        # User turn: checklist fires at generation time (higher attention weight)
        "CONTEXT:\n{context}\n\n"
        "CHECKLIST (thực hiện trước khi viết câu trả lời):\n"
        "\u2022 TRÌNH BÀY DẠNG BẢNG cho mọi thông tin liệt kê (Vai trò-Quyền hạn, Tên-Mô tả, Mốc thời gian-Hành động).\n"
        "\u2022 TUYỆT ĐỐI KHÔNG DÙNG THẺ HTML (DIV, TABLE, BR).\n"
        "\u2022 KIỂM TRA TÁCH BIỆT NGUỒN VÀ BẢNG: Đảm bảo bảng không bị tóm tắt thành text.\n\n"
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

        # ── LangSmith usage metadata ──────────────────────────────────────────
        run = get_current_run_tree()
        if run and hasattr(response, "usage") and response.usage:
            usage_metadata = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            run.add_metadata({
                "ls_provider": "groq",
                "ls_model_type": "chat",
                "ls_model_name": settings.LLM_MODEL,
                "ls_prompt_tokens":      response.usage.prompt_tokens,
                "ls_completion_tokens":  response.usage.completion_tokens,
                "ls_total_tokens":       response.usage.total_tokens,
                "usage_metadata": usage_metadata,
                "complexity":         complexity,
                "prompt_tier":        prompt_tier,
                "max_output_tokens":  max_output_tokens,
            })
            run.add_outputs({"usage_metadata": usage_metadata})

        metadata = {}
        if hasattr(response, "usage") and response.usage:
            metadata = {
                "prompt_tokens":      response.usage.prompt_tokens,
                "completion_tokens":  response.usage.completion_tokens,
                "total_tokens":       response.usage.total_tokens,
            }

        return response.choices[0].message.content, metadata


    # Xóa decorator @traceable ở đây và sử dụng context manager `trace` bên trong
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

        
        with trace(
            name="Groq_Llama3_Stream_Generator",
            run_type="llm",
            inputs={"query": original_query, "context": context, "complexity": complexity, "prompt_tier": prompt_tier}
        ) as rt:
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
    
            full_content = ""
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    text_chunk = chunk.choices[0].delta.content
                    full_content += text_chunk
                    yield text_chunk
                    
            # Đoạn này sẽ chạy khi stream kết thúc
            prompt_tokens = (len(system_tmpl) + len(user_content)) // 4
            completion_tokens = len(full_content) // 4
            total_tokens = prompt_tokens + completion_tokens
            
            rt.end(outputs={
                "output": full_content,
                "usage_metadata": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }
            })
