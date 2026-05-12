import re
import time
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends, Security, BackgroundTasks
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import boto3

from src.pipelines.orchestration import ProductionRAG
from src.pipelines.ingestion import AutoIngestor
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
ingestor: AutoIngestor | None = None

async def register_minio_webhook():
    """Auto-register webhook notification in MinIO."""
    logger.info("[INGESTION] Đang đăng ký MinIO Webhook...")
    s3 = boto3.client(
        "s3",
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=boto3.session.Config(signature_version="s3v4"),
    )
    
    bucket = settings.MINIO_BUCKET
    webhook_arn = "arn:minio:sqs::primary:webhook" # Target 'primary' configured in docker-compose
    
    try:
        # Kiểm tra connectivity & bucket
        s3.head_bucket(Bucket=bucket)
        
        # Đăng ký notification cho cả Created và Removed
        s3.put_bucket_notification_configuration(
            Bucket=bucket,
            NotificationConfiguration={
                'QueueConfigurations': [
                    {
                        'Id': 'AutoIngestionWebhook',
                        'QueueArn': webhook_arn,
                        'Events': ['s3:ObjectCreated:*', 's3:ObjectRemoved:*']
                    }
                ]
            }
        )
        logger.info(f"[INGESTION] Đăng ký webhook thành công cho bucket '{bucket}' -> {webhook_arn} (Created & Removed)")
    except Exception as e:
        logger.warning(f"[INGESTION] Webhook registration failed (Fail-open): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    global rag_engine, ingestor
    logger.info("Đang khởi tạo ProductionRAG Engine...")
    rag_engine = ProductionRAG()
    ingestor = AutoIngestor()
    
    # Register MinIO Webhook
    await register_minio_webhook()
    
    logger.info("Hệ thống RAG đã sẵn sàng nhận request!")
    yield
    # Shutdown logic
    logger.info("Đang dừng hệ thống...")

app = FastAPI(
    title="TechCorp IT Onboarding RAG API",
    description="API phục vụ tra cứu tài liệu nội bộ với kiến trúc Decision-Driven RAG.",
    version="1.3.1",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Webhook Endpoint ---

@app.post("/webhook/minio")
async def minio_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Tiếp nhận event từ MinIO khi có file mới được upload hoặc bị xóa.
    """
    try:
        body = await request.json()
        if "Event" in body and body["Event"] == "s3:TestEvent":
            logger.info("[INGESTION] Nhận TestEvent từ MinIO.")
            return {"status": "ok"}

        records = body.get("Records", [])
        for record in records:
            event_name = record.get("eventName", "")
            bucket = record.get("s3", {}).get("bucket", {}).get("name")
            key = record.get("s3", {}).get("object", {}).get("key")
            
            if bucket and key:
                from urllib.parse import unquote_plus
                key = unquote_plus(key)
                
                if "ObjectCreated" in event_name:
                    logger.info(f"[INGESTION] Nhận event Created: {key}. Đang nạp dữ liệu...")
                    background_tasks.add_task(ingestor.process_single_file, bucket, key)
                elif "ObjectRemoved" in event_name:
                    logger.info(f"[INGESTION] Nhận event Removed: {key}. Đang xóa dữ liệu...")
                    background_tasks.add_task(ingestor.delete_file_data, key)
        
        return {"status": "accepted"}
    except Exception as e:
        logger.error(f"[INGESTION] Lỗi xử lý webhook: {e}")
        return {"status": "error", "message": str(e)}


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
        result = rag_engine.process_with_context(
            chat_request.query, 
            session_id=chat_request.session_id
        )
        answer = result.get("answer", "")
        context = result.get("context", "")
        
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

@app.post("/chat/stream", dependencies=[Depends(verify_api_key)])
async def chat_stream_endpoint(chat_request: ChatRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="Hệ thống chưa sẵn sàng.")

    def stream_generator():
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
