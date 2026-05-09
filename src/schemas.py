from pydantic import BaseModel, Field
from typing import Literal, List, Optional


class Provenance(BaseModel):
    tier: str = Field(description="Tầng xử lý tìm ra kết quả (VD: T1_Path, T2_Scoring, Default)")
    confidence: float = Field(default=1.0, description="Độ tự tin của hệ thống")


class DocumentMetadata(BaseModel):
    document_id: str = Field(...)
    source: str = Field(...)
    category: str = Field(default="General")
    doc_type: str = Field(default="Document")
    security_level: str = Field(default="Internal")
    updated_at: Optional[str] = Field(default=None)

    provenance: Provenance


class ChunkPayload(BaseModel):
    chunk_id: int
    document_id: str
    source: str
    text: str
    category: str
    doc_type: str
    security_level: str
    is_table: bool = Field(default=False)


class QueryAnalysis(BaseModel):
    intent: Literal["technical", "general"]
    complexity_score: float
    ambiguity_score: float
    entities: List[str] = Field(default_factory=list)


class RewrittenQuery(BaseModel):
    search_query: str