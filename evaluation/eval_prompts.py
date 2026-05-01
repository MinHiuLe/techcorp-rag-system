# ───────────────────────────────────────────────────────────────────────────────
# eval_prompts.py — Khắt khe hơn, có few-shot negative, reasoning bắt buộc
# ───────────────────────────────────────────────────────────────────────────────

# Dùng cho context_recall — thay thế embedding-only bằng LLM sentence coverage
CONTEXT_RECALL_PROMPT = """Bạn là chuyên gia đánh giá RAG. Nhiệm vụ: kiểm tra xem GROUND TRUTH có được COVER đầy đủ trong CONTEXT không.

Câu hỏi: {question}
Ground truth (đáp án chuẩn): {ground_truth}
Context (tài liệu retrieve): {context}

HƯỚNG DẪN:
1. Tách ground truth thành các ý then chốt (mỗi ý là 1 mệnh đề hoàn chỉnh).
2. Với mỗi ý, kiểm tra xem context có chứa thông tin tương đương không.
3. Điểm = (số ý được cover) / (tổng số ý).

VÍ DỤ:
Ground truth: "Thời gian tối đa ở stage Legal là 15 ngày. Nếu quá hạn, AE báo cáo hàng ngày lên VP of Sales."
Context: "Stage Legal có thời hạn tối đa 15 ngày. Sau 15 ngày, AE cần báo cáo lên cấp trên."
→ Ý 1: "15 ngày" ✓ | Ý 2: "AE báo cáo hàng ngày" ✓ | Ý 3: "VP of Sales" ✗ (context chỉ nói "cấp trên")
→ context_recall = 2/3 ≈ 0.67

Trả về JSON:
{{
  "reasoning": "Phân tích từng ý...",
  "context_recall": <float 0.0-1.0>
}}
"""

COMBINED_EVAL_PROMPT = """Bạn là giám khảo KHẮT KHE đánh giá hệ thống RAG. ĐỪNG cho điểm cao chỉ vì câu trả lời "nghe có vẻ đúng". Nếu thiếu thông tin quan trọng so với ground truth → PHẢI trừ điểm.

═══════════════════════════════════════════════════════════════
CÂU HỎI: {question}

GROUND TRUTH (chuẩn — chứa TẤT CẢ thông tin cần thiết):
{ground_truth}

CONTEXT (tài liệu retrieve):
{context}

CÂU TRẢ LỜI CỦA HỆ THỐNG:
{generated_answer}
═══════════════════════════════════════════════════════════════

TRƯỚC KHI CHẤM ĐIỂM, bắt buộc viết phân tích theo mẫu:
1. So sánh từng ý then chốt trong ground truth với câu trả lời.
2. Liệt kê những gì CÂU TRẢ LỜI THIẾU so với ground truth.
3. Liệt kê những gì CÂU TRẢ LỜI THÊM không có trong context (hallucination).
4. Dựa trên phân tích trên, chấm điểm.

═══════════════════════════════════════════════════════════════
VÍ DỤ CHẤM ĐIỂM:

[Ví dụ A — Điểm CAO]
Ground truth: "IT thay mực định kỳ. Nhân viên chỉ cần báo ticket nếu >1 ngày chưa xử lý."
Câu trả lời: "IT sẽ thay mực định kỳ hoặc khi nhận cảnh báo từ máy. Bạn không cần tự thay, chỉ cần báo qua ticket nếu máy báo lỗi hơn 1 ngày chưa được xử lý."
Phân tích: Đầy đủ cả 2 ý: (1) IT thay mực, (2) báo ticket nếu >1 ngày. Không hallucination.
→ context_precision: 1.0, strict_faithfulness: 1.0, answer_relevance: 1.0

[Ví dụ B — Điểm THẤP vì THIẾU thông tin]
Ground truth: "Thời gian tối đa ở stage Legal là 15 ngày. Nếu quá hạn, AE báo cáo hàng ngày lên VP of Sales."
Câu trả lời: "Thời gian tối đa là 15 ngày."
Phân tích: THIẾU hoàn toàn ý thứ 2 về "AE báo cáo hàng ngày lên VP of Sales". Đây là thông tin quan trọng.
→ context_precision: 1.0, strict_faithfulness: 1.0, answer_relevance: 0.5

[Ví dụ C — Điểm THẤP vì HALLUCINATION]
Ground truth: "IT thay mực định kỳ. Nhân viên chỉ cần báo ticket."
Câu trả lời: "Nhân viên tự thay mực và báo lại cho quản lý."
Phân tích: Câu trả lời nói "nhân viên tự thay" — HOÀN TOÀN SAI so với ground truth và context. Đây là hallucination nghiêm trọng.
→ context_precision: 1.0, strict_faithfulness: 0.0, answer_relevance: 0.0

[Ví dụ D — Điểm TRUNG BÌNH]
Ground truth: "Đổi mật khẩu AD, email, VPN, Jira, GitHub. Kích hoạt MFA. Thông báo Security Team."
Câu trả lời: "Ngay lập tức đổi mật khẩu AD và tất cả mật khẩu có liên quan. Kích hoạt MFA lại."
Phân tích: Có ý 1 (đổi mật khẩu) và ý 2 (MFA). THIẾU ý 3: "thông báo Security Team kiểm tra log". Không hallucination.
→ context_precision: 1.0, strict_faithfulness: 1.0, answer_relevance: 0.67

═══════════════════════════════════════════════════════════════
RUBRIC CHI TIẾT:

context_precision (float 0.0–1.0):
- 1.0: Mọi đoạn trong context đều hữu ích, không có nhiễu.
- 0.7: Có 1 đoạn không liên quan lắm nhưng không gây hại.
- 0.5: Nửa context hữu ích, nửa không liên quan.
- 0.0: Context hoàn toàn không chứa thông tin cần thiết.

strict_faithfulness (float 0.0–1.0):
- 1.0: Không có bất kỳ thông tin nào ngoài context. Hoàn toàn trung thực.
- 0.7: Có thêm 1 chi tiết nhỏ không có trong context nhưng không sai lệch.
- 0.5: Có 1 câu nói sai hoặc thêm thông tin không được context hỗ trợ.
- 0.0: Có hallucination rõ ràng hoặc trả lời hoàn toàn sai sự thật so với context.

answer_relevance (float 0.0–1.0):
- 1.0: Chứa TẤT CẢ các điểm then chốt trong ground truth. Không thiếu gì.
- 0.75: Thiếu 1 chi tiết PHỤ (không ảnh hưởng lớn).
- 0.5: Thiếu 1 chi tiết QUAN TRỌNG hoặc trả lời chưa đầy đủ.
- 0.25: Thiếu nhiều chi tiết quan trọng hoặc trả lời lấp lửng.
- 0.0: Hoàn toàn lạc đề hoặc trả lời "không có thông tin" khi ground truth có đáp án.

═══════════════════════════════════════════════════════════════
BẮT BUỘC: Trả về JSON với đầy đủ phân tích reasoning (ít nhất 3 câu).

{{
  "reasoning": "Phân tích chi tiết: (1) So sánh với ground truth... (2) Thiếu/Hallucination... (3) Lý do chấm điểm...",
  "context_precision": <float>,
  "strict_faithfulness": <float>,
  "answer_relevance": <float>
}}
"""

RETRIEVAL_EVAL_PROMPT = """DEPRECATED — dùng COMBINED_EVAL_PROMPT hoặc CONTEXT_RECALL_PROMPT thay thế."""
GENERATION_EVAL_PROMPT = """DEPRECATED — dùng COMBINED_EVAL_PROMPT thay thế."""