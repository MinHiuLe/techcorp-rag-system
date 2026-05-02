# ───────────────────────────────────────────────────────────────────────────────
# eval_prompts.py — Unified Judge Prompt (v6)
#
# THAY ĐỔI SO VỚI v5:
#   Trước: 3 LLM calls/sample (recall + combined + completeness) = 60 calls/run
#   Sau:   1 LLM call/sample  (UNIFIED_EVAL_PROMPT)             = 20 calls/run
#
# Lý do gộp được: cả 3 prompt cùng đọc context + answer + ground_truth.
# Tách ra không giúp attention tốt hơn — chỉ tốn token và rate limit.
# ───────────────────────────────────────────────────────────────────────────────


# ── UNIFIED PROMPT (dùng thay thế cho cả 3 prompt cũ) ────────────────────────
UNIFIED_EVAL_PROMPT = """Bạn là giám khảo KHẮT KHE đánh giá hệ thống RAG. Nhiệm vụ: chấm ĐỒNG THỜI 4 metrics trong 1 lần phân tích.

═══════════════════════════════════════════════════════════════
CÂU HỎI: {question}

GROUND TRUTH (đáp án chuẩn — chứa TẤT CẢ thông tin cần thiết):
{ground_truth}

CONTEXT (tài liệu retrieve được):
{context}

CÂU TRẢ LỜI CỦA HỆ THỐNG:
{generated_answer}
═══════════════════════════════════════════════════════════════

BƯỚC 1 — PHÂN TÍCH (bắt buộc trước khi chấm điểm):

A. Tách GROUND TRUTH thành các ý then chốt (đánh số 1, 2, 3...).

B. Với mỗi ý, kiểm tra:
   [CONTEXT]  Ý này có trong context không? → dùng để tính context_recall
   [ANSWER]   Ý này có trong câu trả lời không? → dùng để tính completeness
   Ký hiệu: ✓ = có | ✗ = không | ~ = có một phần

C. Kiểm tra hallucination:
   Liệt kê những gì câu trả lời NÓI THÊM không có trong context.

═══════════════════════════════════════════════════════════════
BƯỚC 2 — CHẤM 4 METRICS:

1. context_recall (float 0.0–1.0):
   = (số ý GT có trong context) / (tổng số ý GT)
   → Đo retrieval có lấy đủ thông tin không.

2. context_precision (float 0.0–1.0):
   - 1.0: Toàn bộ context hữu ích, không có nhiễu
   - 0.7: Có 1-2 đoạn không liên quan
   - 0.5: Nửa context hữu ích
   - 0.0: Context không chứa thông tin cần thiết
   → Đo chất lượng retrieval (có lấy đúng không).

3. strict_faithfulness (float 0.0–1.0):
   - 1.0: Câu trả lời 100% grounded trong context, không bịa
   - 0.7: Có 1 chi tiết nhỏ không có trong context nhưng không sai
   - 0.5: Có 1 câu sai hoặc thêm thông tin không được context hỗ trợ
   - 0.0: Hallucination rõ ràng hoặc mâu thuẫn với context
   → Đo generator có bịa đặt không.

4. answer_completeness (float 0.0–1.0):
   = (số ý GT có trong câu trả lời) / (tổng số ý GT)
   Chú ý: Nếu ý KHÔNG có trong context → không tính (đánh dấu N/A, không trừ điểm completeness).
   → Đo generator có dùng hết thông tin trong context không.

5. issue (string):
   Chọn 1 trong: "OK" | "GENERATOR_MISSED" | "CONTEXT_MISSING" | "HALLUCINATION"
   - OK: Tất cả metrics ≥ 0.7
   - GENERATOR_MISSED: context_recall cao (≥ 0.7) nhưng completeness thấp (< 0.6)
   - CONTEXT_MISSING: context_recall thấp (< 0.5) → retrieval thiếu thông tin
   - HALLUCINATION: strict_faithfulness thấp (< 0.5) → bot bịa đặt

═══════════════════════════════════════════════════════════════
VÍ DỤ:

[Ví dụ 1 — Tốt]
GT: "IT thay mực định kỳ. Nhân viên báo ticket nếu >1 ngày."
Context: "IT thay mực. Nhân viên cần báo ticket nếu máy báo lỗi >1 ngày."
Answer: "IT thay mực định kỳ. Bạn chỉ cần báo ticket nếu máy báo lỗi hơn 1 ngày."
Phân tích:
  Ý 1 "IT thay mực": [CONTEXT] ✓ | [ANSWER] ✓
  Ý 2 "báo ticket >1 ngày": [CONTEXT] ✓ | [ANSWER] ✓
  Hallucination: không có
→ context_recall: 1.0, context_precision: 1.0, strict_faithfulness: 1.0, answer_completeness: 1.0, issue: OK

[Ví dụ 2 — Generator bỏ sót]
GT: "Đổi mật khẩu AD, email, VPN, Jira, GitHub. Kích hoạt MFA. Thông báo Security Team."
Context: "Cần đổi mật khẩu tất cả hệ thống. Kích hoạt MFA. Báo Security Team kiểm tra log."
Answer: "Đổi mật khẩu AD và email. Kích hoạt MFA lại."
Phân tích:
  Ý 1 "đổi mật khẩu": [CONTEXT] ✓ | [ANSWER] ~ (thiếu VPN, Jira, GitHub)
  Ý 2 "kích hoạt MFA": [CONTEXT] ✓ | [ANSWER] ✓
  Ý 3 "thông báo Security Team": [CONTEXT] ✓ | [ANSWER] ✗
  Hallucination: không có
→ context_recall: 1.0, context_precision: 1.0, strict_faithfulness: 1.0, answer_completeness: 0.5, issue: GENERATOR_MISSED

[Ví dụ 3 — Retrieval thiếu]
GT: "Nhân viên mới cần tạo AD account trong 24h đầu. Manager phải approve."
Context: "Nhân viên cần tạo tài khoản sau khi onboard." (không nói 24h, không nói manager)
Answer: "Bạn cần tạo tài khoản sau khi onboard."
Phân tích:
  Ý 1 "24h đầu": [CONTEXT] ✗ | [ANSWER] ✗ (N/A - context thiếu)
  Ý 2 "manager approve": [CONTEXT] ✗ | [ANSWER] ✗ (N/A - context thiếu)
  Ý 3 "tạo AD account": [CONTEXT] ~ | [ANSWER] ✓
→ context_recall: 0.33, context_precision: 0.7, strict_faithfulness: 1.0, answer_completeness: 1.0 (chỉ tính ý có trong context), issue: CONTEXT_MISSING

[Ví dụ 4 — Hallucination]
GT: "IT thay mực định kỳ. Nhân viên chỉ cần báo ticket."
Context: "IT thay mực. Nhân viên báo ticket."
Answer: "Nhân viên tự thay mực và báo lại cho quản lý."
Phân tích:
  Ý 1 "IT thay mực": [CONTEXT] ✓ | [ANSWER] ✗ (bị đảo ngược thành "nhân viên tự thay")
  Hallucination: "nhân viên tự thay mực" — SAI hoàn toàn so với context
→ context_recall: 1.0, context_precision: 1.0, strict_faithfulness: 0.0, answer_completeness: 0.0, issue: HALLUCINATION

═══════════════════════════════════════════════════════════════
QUAN TRỌNG: Bạn PHẢI trả lờI CHỈ bằng JSON thuần (raw JSON), không dùng markdown ```json, không thêm giải thích ngoài JSON.

BẮT BUỘC: Trả về JSON hợp lệ với đúng 6 fields sau:

{{
  "reasoning": "Bước 1A: [liệt kê ý GT]. Bước 1B: [✓/✗ từng ý với context và answer]. Bước 1C: [hallucination nếu có]. Bước 2: [lý do chấm điểm từng metric]",
  "context_recall": <float 0.0-1.0>,
  "context_precision": <float 0.0-1.0>,
  "strict_faithfulness": <float 0.0-1.0>,
  "answer_completeness": <float 0.0-1.0>,
  "issue": "<OK|GENERATOR_MISSED|CONTEXT_MISSING|HALLUCINATION>"
}}
"""


# ── Legacy prompts — giữ lại để backward compatibility ───────────────────────
# Không dùng trong evaluator v6+, nhưng giữ để không break import cũ

CONTEXT_RECALL_PROMPT = """[DEPRECATED - dùng UNIFIED_EVAL_PROMPT thay thế]

Câu hỏi: {question}
Ground truth (đáp án chuẩn): {ground_truth}
Context (tài liệu retrieve): {context}

Trả về JSON:
{{
  "reasoning": "...",
  "context_recall": <float 0.0-1.0>
}}
"""

COMPLETENESS_PROMPT = """[DEPRECATED - dùng UNIFIED_EVAL_PROMPT thay thế]

Ground truth: {ground_truth}
Câu trả lời: {answer}
Context (tài liệu retrieve): {context}

Trả về JSON:
{{
  "reasoning": "...",
  "completeness": <float 0.0-1.0>,
  "issue": "<GENERATOR_MISSED | CONTEXT_MISSING | OK>"
}}
"""

COMBINED_EVAL_PROMPT = """[DEPRECATED - dùng UNIFIED_EVAL_PROMPT thay thế]

CÂU HỎI: {question}
GROUND TRUTH: {ground_truth}
CONTEXT: {context}
CÂU TRẢ LỜI: {generated_answer}

Trả về JSON:
{{
  "reasoning": "...",
  "context_precision": <float>,
  "strict_faithfulness": <float>
}}
"""

RETRIEVAL_EVAL_PROMPT  = "[DEPRECATED]"
GENERATION_EVAL_PROMPT = "[DEPRECATED]"