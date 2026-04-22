RETRIEVAL_EVAL_PROMPT = """
Bạn là giám khảo đánh giá hệ thống RAG. Nhiệm vụ: Đánh giá chất lượng của TÀI LIỆU TRÍCH XUẤT (Context).

CÂU HỎI: {question}
CÂU TRẢ LỜI KỲ VỌNG (Ground Truth): {ground_truth}
TÀI LIỆU TRÍCH XUẤT (Context):
{context}

Tiêu chí:
1. context_recall (0 hoặc 1): TÀI LIỆU TRÍCH XUẤT có chứa đủ thông tin để tạo ra CÂU TRẢ LỜI KỲ VỌNG không?
2. context_precision (0.0 đến 1.0): Tỷ lệ các đoạn văn bản trong TÀI LIỆU TRÍCH XUẤT thực sự đóng góp vào việc trả lời câu hỏi là bao nhiêu?

BẮT BUỘC TRẢ VỀ JSON CHÍNH XÁC THEO FORMAT SAU:
{{
  "context_recall": <int>,
  "context_precision": <float>,
  "reasoning": "<string: Giải thích ngắn gọn lý do cho số điểm trên>"
}}
"""

GENERATION_EVAL_PROMPT = """
Bạn là giám khảo đánh giá hệ thống RAG. Nhiệm vụ: Đánh giá chất lượng của CÂU TRẢ LỜI (Answer) do AI sinh ra.

CÂU HỎI: {question}
TÀI LIỆU TRÍCH XUẤT (Context):
{context}
CÂU TRẢ LỜI CẦN ĐÁNH GIÁ: {generated_answer}

Tiêu chí:
1. strict_faithfulness (0 hoặc 1): CÂU TRẢ LỜI có dựa 100% vào TÀI LIỆU TRÍCH XUẤT không? Nếu có chi tiết bịa đặt -> 0. Nếu từ chối trả lời vì không có tài liệu -> 1.
2. answer_relevance (0.0 đến 1.0): CÂU TRẢ LỜI đi thẳng vào vấn đề của CÂU HỎI tốt đến mức nào?

BẮT BUỘC TRẢ VỀ JSON CHÍNH XÁC THEO FORMAT SAU:
{{
  "strict_faithfulness": <int>,
  "answer_relevance": <float>,
  "reasoning": "<string: Giải thích ngắn gọn lý do cho số điểm trên>"
}}
"""