from dotenv import load_dotenv
load_dotenv()

import re
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.pipelines.orchestration import ProductionRAG
from src.utils.pii_scrubber import scrub
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate Limiting setup
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)

# API Key Auth setup
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not settings.API_KEYS:
        return # Allow all if no keys configured
    valid_keys = [k.strip() for k in settings.API_KEYS.split(",") if k.strip()]
    if not valid_keys:
        return
    if api_key not in valid_keys:
        raise HTTPException(
            status_code=403, 
            detail="Bạn không có quyền truy cập API này. Vui lòng cung cấp X-API-Key hợp lệ."
        )

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
    version="1.2.0",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/keys/status", dependencies=[Depends(verify_api_key)])
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
    context: str | None = None
    latency_seconds: float
    status: str = "success"


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    context: str | None = None
    is_positive: bool
    session_id: str = "default"
    source: str | None = None


def _extract_sources(context: str) -> str | None:
    if not context or context == "⚡ Semantic Cache Hit":
        return None
    matches = re.findall(r"\[Nguồn:\s*(.+?)\]", context)
    return ", ".join(dict.fromkeys(matches)) or None


@app.get("/health")
async def health_check():
    if not rag_engine:
        return {"status": "starting", "healthy": False}
    
    report = rag_engine.health_check()
    report["cache"] = rag_engine.cache.stats()
    return report


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit("20/minute")
async def chat_endpoint(request: Request, chat_request: ChatRequest):
    if not rag_engine:
        raise HTTPException(
            status_code=503,
            detail="Hệ thống đang khởi động, vui lòng thử lại sau.",
        )

    start_time = time.time()
    try:
        answer, context = rag_engine.process_with_context(
            chat_request.query, 
            session_id=chat_request.session_id
        )
        
        # Detect maintenance messages from engine to return 503 instead of 200
        maintenance_keywords = [
            "sự cố kết nối", "bảo trì hạ tầng", "quá tải", "thử lại sau"
        ]
        if any(kw in answer for kw in maintenance_keywords) and not context:
             raise HTTPException(status_code=503, detail=answer)

        scrubbed = scrub(answer)
        if scrubbed.hits > 0:
            logger.warning("[PII] %d match(es) scrubbed | session=%s",
                           scrubbed.hits, chat_request.session_id)
        answer = scrubbed.text

        source = _extract_sources(context)
        latency = round(time.time() - start_time, 2)

        logger.info(f"[{chat_request.session_id}] {latency}s | source={source}")

        return ChatResponse(
            answer=answer,
            source=source,
            context=context,
            latency_seconds=latency,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi xử lý query: {e}")
        raise HTTPException(status_code=500, detail="Lỗi nội bộ hệ thống RAG.")


@app.post("/chat/feedback", dependencies=[Depends(verify_api_key)])
async def feedback_endpoint(feedback: FeedbackRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")
    
    try:
        rag_engine.memory.save_feedback(
            session_id=feedback.session_id,
            query=feedback.query,
            answer=feedback.answer,
            context=feedback.context or "",
            is_positive=feedback.is_positive,
            source=feedback.source
        )
        return {"status": "success", "message": "Cảm ơn bạn đã phản hồi!"}
    except Exception as e:
        logger.error(f"Lỗi lưu phản hồi: {e}")
        raise HTTPException(status_code=500, detail="Không thể lưu phản hồi.")


from fastapi.responses import StreamingResponse
import json

@app.post("/chat/stream", dependencies=[Depends(verify_api_key)])
async def chat_stream_endpoint(chat_request: ChatRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")

    def stream_generator():
        # Trích xuất source sau khi có context hoàn chỉnh
        # Vì context có ngay từ đầu sau khi retrieval xong (trước khi gen bắt đầu)
        # Chúng ta sẽ gửi context/source ở chunk đầu tiên dưới dạng JSON metadata
        context_sent = False
        
        for chunk, context in rag_engine.process_with_context_stream(
            chat_request.query, 
            session_id=chat_request.session_id
        ):
            if not context_sent:
                source = _extract_sources(context)
                metadata = {
                    "type": "metadata",
                    "source": source,
                    "context": context
                }
                yield json.dumps(metadata) + "\n"
                context_sent = True
            
            yield json.dumps({"type": "content", "content": chunk}) + "\n"

    return StreamingResponse(stream_generator(), media_type="application/x-ndjson")


@app.delete("/chat/memory/{session_id}")
async def clear_memory_endpoint(session_id: str = "default"):
    if rag_engine:
        rag_engine.clear_memory(session_id)
    return {"status": f"Memory cleared for session {session_id}."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
