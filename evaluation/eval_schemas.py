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


# ── Schema cho combined evaluator (v5.2) ──────────────────────────────────────
# CHANGED: Bỏ answer_relevance khỏi combined, chỉ giữ precision + faithfulness

class CombinedEvalResult(BaseModel):
    context_precision:   float = Field(
        ge=0.0, le=1.0,
        description="Tỷ lệ context thực sự hữu ích (0.0 = toàn nhiễu, 1.0 = hoàn hảo)."
    )
    strict_faithfulness: float = Field(
        ge=0.0, le=1.0,
        description="Mức độ trung thực với context (0.0 = hallucination nặng, 1.0 = hoàn toàn grounded)."
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


# ── NEW: Schema cho completeness ───────────────────────────────────────────────
from pydantic import BaseModel, Field, field_validator


class CompletenessResult(BaseModel):
    completeness: float = Field(
        ge=0.0, le=1.0,
        description="Tỷ lệ ý then chốt trong GT được cover bởi câu trả lời."
    )
    reasoning: str = Field(
        description="Liệt kê từng ý ✓/✗/MISSED/N/A."
    )
    issue: str = Field(
        default="OK",
        description="Root cause: GENERATOR_MISSED | CONTEXT_MISSING | OK"
    )

    @field_validator('reasoning', mode='before')
    @classmethod
    def convert_reasoning_to_string(cls, v):
        """Convert list/dict to string if judge returns malformed JSON."""
        if isinstance(v, list):
            return " | ".join(str(item) for item in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return str(v) if v is not None else ""

    @field_validator('issue', mode='before')
    @classmethod
    def normalize_issue(cls, v):
        """Ensure issue is always a valid string."""
        valid_issues = {"GENERATOR_MISSED", "CONTEXT_MISSING", "OK", "UNKNOWN"}
        v = str(v).upper().replace("-", "_")
        if v not in valid_issues:
            return "UNKNOWN"
        return v