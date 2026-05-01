from pydantic import BaseModel, Field


class RetrievalEvalResult(BaseModel):
    """Schema cũ — giữ lại cho backward compatibility."""
    context_recall: int = Field(ge=0, le=1, description="1: Đủ thông tin. 0: Thiếu.")
    context_precision: float = Field(ge=0.0, le=1.0)
    reasoning: str


class GenerationEvalResult(BaseModel):
    """Schema cũ — giữ lại cho backward compatibility."""
    strict_faithfulness: int = Field(ge=0, le=1, description="1: 100% grounded. 0: Hallucinate.")
    answer_relevance: float = Field(ge=0.0, le=1.0)
    reasoning: str


# ── Schema MỚI cho combined evaluator (v5) ────────────────────────────────────
# strict_faithfulness chuyển từ int → float để có variance

class CombinedEvalResult(BaseModel):
    context_precision:   float = Field(
        ge=0.0, le=1.0,
        description="Tỷ lệ context thực sự hữu ích (0.0 = toàn nhiễu, 1.0 = hoàn hảo)."
    )
    strict_faithfulness: float = Field(
        ge=0.0, le=1.0,
        description="Mức độ trung thực với context (0.0 = hallucination nặng, 1.0 = hoàn toàn grounded)."
    )
    answer_relevance:    float = Field(
        ge=0.0, le=1.0,
        description="Độ đầy đủ so với ground truth (0.0 = lạc đề, 1.0 = đầy đủ mọi ý)."
    )
    reasoning:           str   = Field(
        description="Phân tích chi tiết: so sánh với GT, liệt kê thiếu/hallucination, lý do chấm điểm."
    )


# ── Schema cho context_recall LLM-based ────────────────────────────────────────

class ContextRecallResult(BaseModel):
    context_recall: float = Field(
        ge=0.0, le=1.0,
        description="Tỷ lệ ý then chốt trong GT được cover bởi context."
    )
    reasoning: str = Field(
        description="Liệt kê từng ý trong GT và đánh dấu ✓/✗."
    )