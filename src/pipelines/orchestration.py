import os
from groq import Groq
import cohere
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from langsmith import traceable

from config.settings import settings
from src.core.analyzer import QueryAnalyzer
from src.core.rewriter import QueryRewriter
from src.core.context_builder import ContextBuilder
from src.core.generator import Generator
from src.retrieval.engine import RetrievalStrategyEngine, RetrievalEngine
from src.retrieval.reranker import RerankPolicyEngine
from src.retrieval.cache import SemanticCache
from src.utils.text_utils import clean_text

class ProductionRAG:
    def __init__(self):
        # 1. Khởi tạo các API Clients (Lấy key từ settings)
        self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
        self.cohere_client = cohere.Client(api_key=settings.COHERE_API_KEY)
        self.qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=60)
        
        # 2. Khởi tạo Local Embedding Models
        self.dense_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        
        # 3. Khởi tạo các Modules lõi
        self.analyzer = QueryAnalyzer(self.groq_client)
        self.rewriter = QueryRewriter(self.groq_client)
        self.retriever = RetrievalEngine(self.qdrant_client, self.dense_model, self.sparse_model)
        self.policy = RerankPolicyEngine(self.cohere_client)
        self.generator = Generator(self.groq_client)
        
        # 4. Quản lý bộ nhớ đa lượt
        self.memory = []

        self.cache = SemanticCache(threshold=0.85)

    def clear_memory(self):
        """Xóa sạch trí nhớ để đánh giá các câu hỏi độc lập không bị nhiễu."""
        self.memory = []

    def _get_formatted_history(self) -> str:
        if not self.memory: return "Không có."
        return "\n".join([f"User: {m['user']}\nBot: {m['bot']}" for m in self.memory])
    
    @traceable(run_type="chain", name="RAG_Core_Pipeline")
    def process_with_context(self, raw_query: str) -> tuple[str, str]:
        """Luồng chính: Trả về cả Answer và Context (Phục vụ Evaluation)."""
        query = clean_text(raw_query)
        history_str = self._get_formatted_history()

        # --- [MỚI] BƯỚC 0: SEMANTIC CACHE CHECK ---
        # Dùng mô hình SentenceTransformer hiện có để nén câu hỏi
        query_embedding = self.dense_model.encode(query).tolist()
        
        cached_answer = self.cache.check(query_embedding)
        if cached_answer:
            # Nếu tìm thấy, trả về ngay lập tức (Bỏ qua toàn bộ LLM và Database)
            self.memory.append({"user": query, "bot": cached_answer})
            return cached_answer, "⚡ [Trích xuất từ Bộ nhớ đệm Semantic Cache - Không tốn Token API]"
        # ------------------------------------------

        # 1. Analyzer
        analysis = self.analyzer.analyze(query, history_str)

        if analysis.intent == "general":
            final_answer = "Xin chào! Tôi là hệ thống AI nội bộ TechCorp. Tôi có thể giúp bạn tra cứu tài liệu gì hôm nay?"
            final_context = ""
        else:
            # 2. Rewriter
            search_query = self.rewriter.rewrite(query, analysis, history_str)
            
            # 3. Retrieval Strategy & Search
            strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)
            raw_docs = self.retriever.search(search_query, strategy, fetch_k)
            
            # 4. Rerank Policy
            ranked_docs = self.policy.apply_policy(search_query, raw_docs, analysis)
            
            # 5. Build Context
            final_context = ContextBuilder.build(ranked_docs)
            
            if not final_context:
                final_answer = "Hệ thống chưa có tài liệu về vấn đề này."
            else:
                # 6. Generator
                final_answer = self.generator.generate(query, final_context)

        # Nếu bot trả lời thành công (không phải câu chối từ), ta lưu vào Cache
        if final_context and analysis.intent != "general":
            self.cache.add(query, query_embedding, final_answer)
        # ------------------------------------------

        # Cập nhật Memory (Giữ 3 lượt)
        self.memory.append({"user": query, "bot": final_answer})
        if len(self.memory) > 3:
            self.memory.pop(0)

        return final_answer, final_context

    def process(self, raw_query: str) -> str:
        """Luồng chính: Chỉ trả về Answer (Phục vụ API/UI)."""
        answer, _ = self.process_with_context(raw_query)
        return answer

# ==========================================
# MAIN EXECUTION (TERMINAL CLI)
# ==========================================
if __name__ == "__main__":
    print("\n" + "#"*60)
    print("🚀 TECHCORP DECISION-DRIVEN RAG (CLI MODE)")
    print("#"*60)
    print("Gõ 'exit', 'q', hoặc 'quit' để thoát.\n")
    
    app = ProductionRAG()

    while True:
        user_input = input("👤 User: ")
        if user_input.lower() in ["exit", "q", "quit"]: 
            print("Tạm biệt!")
            break
        try:
            # Gọi hàm process để lấy câu trả lời
            result = app.process(user_input)
            print(f"\n🤖 Bot:\n{result}\n")
            print("-" * 50)
        except Exception as e:
            print(f"\n❌ [LỖI HỆ THỐNG]: {e}\n")