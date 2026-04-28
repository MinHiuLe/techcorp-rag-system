RETRIEVAL_EVAL_PROMPT = """Bạn là giám khảo RAG. Đánh giá TÀI LIỆU TRÍCH XUẤT theo 2 tiêu chí và trả về JSON.
 
CÂU HỎI: {question}
GROUND TRUTH: {ground_truth}
CONTEXT: {context}
 
Tiêu chí:
- context_recall (0 hoặc 1): Context có đủ thông tin để tạo ra Ground Truth không?
- context_precision (0.0–1.0): Tỷ lệ đoạn văn trong Context thực sự hữu ích để trả lời câu hỏi.
 
NGHIÊM CẤM bịa thêm thông tin ngoài Context. Trả về đúng format:
{{"context_recall": <int>, "context_precision": <float>, "reasoning": "<string>"}}"""

GENERATION_EVAL_PROMPT = """Bạn là giám khảo RAG. Đánh giá CÂU TRẢ LỜI theo 2 tiêu chí và trả về JSON.
 
CÂU HỎI: {question}
CONTEXT: {context}
CÂU TRẢ LỜI: {generated_answer}
 
Tiêu chí:
- strict_faithfulness (0 hoặc 1): Câu trả lời có dựa 100% vào Context không? Có chi tiết bịa đặt → 0.
- answer_relevance (0.0–1.0): Câu trả lời có đi thẳng vào câu hỏi không?
 
Trả về đúng format:
{{"strict_faithfulness": <int>, "answer_relevance": <float>, "reasoning": "<string>"}}"""


# ── Combined prompt: gộp retrieval precision + generation vào 1 LLM call ───────
# Dùng cho evaluator v4 trở đi. Recall tính riêng bằng embedding (không tốn token).

COMBINED_EVAL_PROMPT = """\
You are a RAG evaluation judge. Score the following across 3 metrics and return ONE JSON.

QUESTION: {question}
GROUND TRUTH: {ground_truth}
RETRIEVED CONTEXT: {context}
GENERATED ANSWER: {generated_answer}

## Metrics

1. context_precision (float 0.0–1.0)
   What fraction of the retrieved context is actually relevant to answering the question?
   1.0 = every sentence useful | 0.0 = entirely irrelevant

2. strict_faithfulness (int 0 or 1)
   Does the answer contain ONLY information supported by the context?
   1 = fully grounded | 0 = any hallucinated claim

3. answer_relevance (float 0.0–1.0)
   How directly and completely does the answer address the question?
   1.0 = perfect | 0.0 = off-topic

4. reasoning (string)
   One sentence explaining all three scores together.

Return ONLY valid JSON, no markdown, no preamble:
{{
  "context_precision": <float>,
  "strict_faithfulness": <int>,
  "answer_relevance": <float>,
  "reasoning": "<string>"
}}
"""