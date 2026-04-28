from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import time
import logging

from src.pipelines.orchestration import ProductionRAG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TechCorp IT Onboarding RAG API",
    description="API phục vụ tra cứu tài liệu nội bộ với kiến trúc Decision-Driven RAG.",
    version="1.0.0"
)

rag_engine = None

@app.on_event("startup")
async def startup_event():
    global rag_engine
    logger.info("Đang khởi tạo ProductionRAG Engine...")
    rag_engine = ProductionRAG()
    logger.info("Hệ thống RAG đã sẵn sàng nhận request!")

# ==========================================
# SCHEMAS CHO API
# ==========================================
class ChatRequest(BaseModel):
    query: str = Field(..., description="Câu hỏi của người dùng")
    session_id: str = Field(default="default", description="ID phiên chat (để quản lý memory sau này)")

class ChatResponse(BaseModel):
    answer: str
    latency_seconds: float
    status: str = "success"

# ==========================================
# ENDPOINTS
# ==========================================
@app.get("/health")
async def health_check():
    return {"status": "healthy", "model_loaded": rag_engine is not None}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not rag_engine:
        raise HTTPException(status_code=503, detail="Hệ thống đang khởi động, vui lòng thử lại sau.")
    
    start_time = time.time()
    try:
        answer = rag_engine.process(request.query)
        
        latency = round(time.time() - start_time, 2)
        logger.info(f"[{request.session_id}] Query processed in {latency}s")
        
        return ChatResponse(
            answer=answer,
            latency_seconds=latency
        )
    except Exception as e:
        logger.error(f"Lỗi xử lý query: {str(e)}")
        raise HTTPException(status_code=500, detail="Lỗi nội bộ hệ thống RAG.")

@app.delete("/chat/memory")
async def clear_memory_endpoint():
    if rag_engine:
        rag_engine.clear_memory()
    return {"status": "Memory cleared."}