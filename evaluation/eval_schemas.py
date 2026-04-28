from pydantic import BaseModel, Field


class RetrievalEvalResult(BaseModel):
    context_recall: int = Field(ge=0, le=1, description="1: Đủ thông tin. 0: Thiếu thông tin.")
    context_precision: float = Field(ge=0.0, le=1.0, description="Tỷ lệ chunk hữu ích / tổng số chunk.")
    reasoning: str = Field(description="Giải thích ngắn gọn lý do chấm điểm.")


class GenerationEvalResult(BaseModel):
    strict_faithfulness: int = Field(ge=0, le=1, description="1: 100% chi tiết có trong context. 0: Bịa đặt/Ảo giác.")
    answer_relevance: float = Field(ge=0.0, le=1.0, description="Độ sát nghĩa với câu hỏi (0.0 -> 1.0).")
    reasoning: str = Field(description="Giải thích ngắn gọn lý do chấm điểm.")


# ── Schema mới cho combined evaluator (v4) ──────────────────────────────────────

class CombinedEvalResult(BaseModel):
    context_precision:   float = Field(ge=0.0, le=1.0, description="Tỷ lệ context thực sự hữu ích.")
    strict_faithfulness: int   = Field(ge=0,   le=1,   description="1: không hallucinate. 0: có hallucination.")
    answer_relevance:    float = Field(ge=0.0, le=1.0, description="Độ sát nghĩa với câu hỏi.")
    reasoning:           str   = Field(description="Giải thích ngắn gọn cho cả 3 metrics.")