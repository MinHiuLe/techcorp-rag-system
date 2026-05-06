from dotenv import load_dotenv
load_dotenv()

import re
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.pipelines.orchestration import ProductionRAG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rag_engine: ProductionRAG | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    global rag_engine
    logger.info("Đang khởi tạo ProductionRAG Engine...")
    rag_engine = ProductionRAG()
    logger.info("Hệ thống RAG đã sẵn sàng nhận request!")
    yield
    # Shutdown logic (nếu cần)
    logger.info("Đang dừng hệ thống...")

app = FastAPI(
    title="TechCorp IT Onboarding RAG API",
    description="API phục vụ tra cứu tài liệu nội bộ với kiến trúc Decision-Driven RAG.",
    version="1.1.0",
    lifespan=lifespan
)

@app.get("/keys/status")
async def key_status():
    if not rag_engine:
         raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")
    return rag_engine.groq_client.status()


class ChatRequest(BaseModel):
    query: str = Field(..., description="Câu hỏi của người dùng")
    session_id: str = Field(default="default", description="ID phiên chat")


class ChatResponse(BaseModel):
    answer: str
    source: str | None = None
    latency_seconds: float
    status: str = "success"


def _extract_sources(context: str) -> str | None:
    if not context or context == "⚡ Semantic Cache Hit":
        return None
    matches = re.findall(r"\[Nguồn:\s*(.+?)\]", context)
    return ", ".join(dict.fromkeys(matches)) or None


@app.get("/health")
async def health_check():
    cache_stats = rag_engine.cache.stats() if rag_engine else {}
    return {
            "status": "healthy",
            "model_loaded": rag_engine is not None,
            "cache": cache_stats,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not rag_engine:
        raise HTTPException(
            status_code=503,
            detail="Hệ thống đang khởi động, vui lòng thử lại sau.",
        )

    start_time = time.time()
    try:
        answer, context = rag_engine.process_with_context(
            request.query, 
            session_id=request.session_id
        )
        source = _extract_sources(context)
        latency = round(time.time() - start_time, 2)

        logger.info(f"[{request.session_id}] {latency}s | source={source}")

        return ChatResponse(
            answer=answer,
            source=source,
            latency_seconds=latency,
        )

    except Exception as e:
        logger.error(f"Lỗi xử lý query: {e}")
        raise HTTPException(status_code=500, detail="Lỗi nội bộ hệ thống RAG.")


@app.delete("/chat/memory/{session_id}")
async def clear_memory_endpoint(session_id: str = "default"):
    if rag_engine:
        rag_engine.clear_memory(session_id)
    return {"status": f"Memory cleared for session {session_id}."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)