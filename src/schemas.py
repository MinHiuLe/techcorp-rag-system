from pydantic import BaseModel, Field
from typing import Literal, List, Optional

class DocumentMetadata(BaseModel):
    source: str           
    category: str         
    chunk_id: int   

class QueryAnalysis(BaseModel):
    """Lớp đầu ra của QueryAnalyzer - Chỉ làm nhiệm vụ hiểu"""
    intent: Literal["technical", "general"] = Field(description="Phân loại mục đích của user.")
    complexity_score: float = Field(ge=0.0, le=1.0, description="Độ khó của câu hỏi.")
    ambiguity_score: float = Field(ge=0.0, le=1.0, description="Độ mập mờ, thiếu thông tin.")
    entities: List[str] = Field(default_factory=list, description="Danh sách từ khóa kỹ thuật, mã lỗi, tên riêng.")

class RewrittenQuery(BaseModel):
    """Lớp đầu ra của QueryRewriter - Chỉ làm nhiệm vụ tối ưu hóa câu lệnh search"""
    search_query: str = Field(description="Câu hỏi đã được giải ngọng và bổ sung keyword để search.")