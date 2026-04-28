import os
import sys
import json
import unicodedata

# Cấu hình đường dẫn gốc
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from groq import Groq
from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, SparseVector, FusionQuery, Fusion
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from pydantic import ValidationError
import cohere

# Import Schema
from src.schemas import QueryAnalysis, RewrittenQuery

load_dotenv()

# ==========================================
# CONFIG & UTILS
# ==========================================
class Config:
    LLM_MODEL = "llama-3.3-70b-versatile"
    COLLECTION_NAME = "techcorp_knowledge"
    MAX_CONTEXT_LENGTH = 3000

def clean_text(text: str) -> str:
    if not text: return ""
    text = str(text)
    text = unicodedata.normalize("NFC", text)
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore").strip()

# ==========================================
# LAYER 1: QUERY ANALYZER (NÃO BỘ PHÂN TÍCH)
# ==========================================
class QueryAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client

    def analyze(self, query: str, history: str = "") -> QueryAnalysis:
        prompt = f"""
Phân tích câu hỏi HIỆN TẠI của người dùng dựa trên LỊCH SỬ HỘI THOẠI (nếu có) và trả về JSON:
1. Intent: 'technical' (Tra cứu mọi loại tài liệu, quy trình, IT, nghiệp vụ, nhân sự) hoặc 'general' (CHỈ DÀNH CHO chào hỏi giao tiếp như "hello", "hi", "bạn là ai").
2. Complexity Score: 0.0 (rất dễ, 1 fact) -> 1.0 (rất khó, cần so sánh/tổng hợp).
3. Ambiguity Score: 0.0 (rõ ràng) -> 1.0 (mập mờ, dùng đại từ thay thế như "nó", "đó", "cái kia").
4. Entities: Mảng từ khóa kỹ thuật, mã lỗi (vd: ["Docker", "Jira"]). NẾU câu hỏi dùng đại từ (vd: "nó"), hãy trích xuất Entity từ LỊCH SỬ.

LỊCH SỬ HỘI THOẠI GẦN ĐÂY:
{history}

CÂU HỎI HIỆN TẠI: {query}
"""
        response = self.llm.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        try:
            return QueryAnalysis(**json.loads(response.choices[0].message.content))
        except ValidationError:
            return QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.5, entities=[])


# ==========================================
# LAYER 2: QUERY REWRITER (TỐI ƯU CÂU LỆNH)
# ==========================================
class QueryRewriter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def rewrite(self, query: str, analysis: QueryAnalysis, history: str = "") -> str:
        if analysis.complexity_score < 0.2 and analysis.ambiguity_score < 0.3:
            return query

        prompt = f"""
Viết lại CÂU HỎI HIỆN TẠI để tối ưu cho công cụ tìm kiếm tài liệu (Vector Search).
- NẾU câu hỏi dùng từ thay thế ("nó", "quy trình này"), hãy ĐỌC LỊCH SỬ để thay thế bằng danh từ gốc.
- Bổ sung các Entities sau vào câu: {analysis.entities}
- Bỏ các từ giao tiếp thừa thãi. Chỉ trả về duy nhất chuỗi văn bản đã rewrite.

LỊCH SỬ HỘI THOẠI GẦN ĐÂY:
{history}

CÂU HỎI HIỆN TẠI: {query}
"""
        response = self.llm.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

# ==========================================
# LAYER 3 & 4: RETRIEVAL STRATEGY & ENGINE
# ==========================================
class RetrievalStrategyEngine:
    @staticmethod
    def get_strategy(analysis: QueryAnalysis):
        # 1. Top-K retrieval: Luôn lấy một lượng lớn (k=15-20) để tạo phễu lọc
        fetch_k = 20 

        strategy = "hybrid" 
        return strategy, fetch_k

class RetrievalEngine:
    def __init__(self, db_client, dense_model, sparse_model):
        self.db = db_client
        self.dense = dense_model
        self.sparse = sparse_model

    def search(self, query: str, strategy: str, fetch_k: int):
        dense_vec = self.dense.encode(query).tolist()
        sparse_embedding = list(self.sparse.embed([query]))[0]
        sparse_vec = SparseVector(
            indices=sparse_embedding.indices.tolist(), 
            values=sparse_embedding.values.tolist()
        )

        if strategy == "dense":
            results = self.db.query_points(
                collection_name=Config.COLLECTION_NAME,
                query=dense_vec,
                using="dense",
                limit=fetch_k,
                with_payload=True
            )
        else:
            # HYBRID SEARCH (RRF Fusion)
            results = self.db.query_points(
                collection_name=Config.COLLECTION_NAME,
                prefetch=[
                    Prefetch(query=dense_vec, using="dense", limit=fetch_k),
                    Prefetch(query=sparse_vec, using="sparse", limit=fetch_k),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=fetch_k,
                with_payload=True
            )
            
        if not results or not results.points: return []
        return [{"text": clean_text(h.payload.get("text", "")), "source": h.payload.get("source", "Unknown")} for h in results.points]

# ==========================================
# LAYER 5: RERANK POLICY ENGINE
# ==========================================
class RerankPolicyEngine:
    def __init__(self, rerank_client):
        self.reranker = rerank_client
        # 4. Tách mode: Lấy biến môi trường để xác định chạy Eval hay Prod
        self.is_eval_mode = os.getenv("EVAL_MODE", "false").lower() == "true"

    def apply_policy(self, query: str, documents: list, analysis: QueryAnalysis) -> list:
        if not documents: return []

        docs_to_rerank = documents[:15]
        docs_str = [f"SOURCE: {d['source']}\n{d['text']}" for d in docs_to_rerank]
        
        # Gọi API Cohere
        reranked = self.reranker.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs_str,
            top_n=5 # Lấy tối đa top 5 sau rerank
        )

        # 3. Giảm noise bằng Hard Constraint
        final_context = []
        
        # Thiết lập threshold: Chặt chẽ hơn trong Eval, linh hoạt hơn chút ở Prod
        threshold = 0.50 if self.is_eval_mode else 0.40

        for r in reranked.results:
            if r.relevance_score >= threshold:
                final_context.append(docs_to_rerank[r.index])
            
            # Max context chunks: 3-5 (Hard stop)
            if len(final_context) >= 4:
                break

        print(f"  [Policy] Đã lọc qua Reranker. Giữ lại {len(final_context)} chunks (Score >= {threshold}).")
        return final_context

# ==========================================
# LAYER 6: CONTEXT BUILDER (COMPRESSION)
# ==========================================
class ContextBuilder:
    @staticmethod
    def build(documents: list) -> str:
        if not documents: return ""
        
        seen_texts = set()
        unique_docs = []
        for doc in documents:
            if doc['text'] not in seen_texts:
                seen_texts.add(doc['text'])
                unique_docs.append(doc)

        context_parts = []
        current_length = 0
        for doc in unique_docs:
            snippet = f"[Nguồn: {doc['source']}]\n{doc['text']}\n---"
            if current_length + len(snippet) > Config.MAX_CONTEXT_LENGTH:
                print("  [Builder] Token Limit Reached -> Truncating Context")
                break
            context_parts.append(snippet)
            current_length += len(snippet)

        return "\n".join(context_parts)

# ==========================================
# LAYER 7: GENERATOR
# ==========================================
class Generator:
    def __init__(self, llm_client):
        self.llm = llm_client

    def generate(self, original_query: str, context: str) -> str:
        prompt = f"""
Bạn là AI Engineer nội bộ của TechCorp. Dựa vào tài liệu dưới đây, hãy trả lời câu hỏi.
NẾU KHÔNG CÓ THÔNG TIN: Hãy nói "Hệ thống chưa có tài liệu về vấn đề này" và TUYỆT ĐỐI KHÔNG trích dẫn nguồn.
NGƯỢC LẠI: BẮT BUỘC trích dẫn [Nguồn: tên_file] ở cuối câu trả lời.

CONTEXT:
{context}

QUESTION:
{original_query}
"""
        response = self.llm.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return response.choices[0].message.content

# ==========================================
# ORCHESTRATOR: DECISION-DRIVEN PIPELINE
# ==========================================
class ProductionRAG:
    def __init__(self):
        # ... (giữ nguyên các phần init client và layers của bạn) ...
        self.groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.qdrant = QdrantClient(url="http://localhost:6333", timeout=60)
        self.dense = SentenceTransformer("AITeamVN/Vietnamese_Embedding")
        self.sparse = SparseTextEmbedding(model_name="Qdrant/bm25")
        self.cohere = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
        
        self.analyzer = QueryAnalyzer(self.groq)
        self.rewriter = QueryRewriter(self.groq)
        self.retriever = RetrievalEngine(self.qdrant, self.dense, self.sparse)
        self.policy = RerankPolicyEngine(self.cohere)
        self.generator = Generator(self.groq)
        
        # THÊM MỚI: Khởi tạo bộ nhớ
        self.memory = [] 

    def _get_formatted_history(self) -> str:
        if not self.memory: return "Không có."
        return "\n".join([f"User: {m['user']}\nBot: {m['bot']}" for m in self.memory])

    def process(self, raw_query: str) -> str:
        print("\n" + "="*50)
        query = clean_text(raw_query)
        history_str = self._get_formatted_history() # Lấy lịch sử

        # 1. Understanding (Truyền lịch sử vào)
        analysis = self.analyzer.analyze(query, history_str)
        print(f"[*] ANALYZER : Intent={analysis.intent.upper()} | Ambiguity={analysis.ambiguity_score} | Entities={analysis.entities}")

        if analysis.intent == "general":
            final_answer = "Xin chào! Tôi là hệ thống AI nội bộ TechCorp. Tôi có thể giúp bạn tra cứu tài liệu gì hôm nay?"
        else:
            # 2. Query Rewrite (Truyền lịch sử vào)
            search_query = self.rewriter.rewrite(query, analysis, history_str)
            print(f"[*] REWRITER : '{search_query}'")

            # 3. Retrieval Strategy & Search
            strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)
            print(f"[*] STRATEGY : Mode={strategy.upper()} | Fetch={fetch_k}")
            raw_docs = self.retriever.search(search_query, strategy, fetch_k)

            # 4. Rerank Policy
            ranked_docs = self.policy.apply_policy(search_query, raw_docs, analysis)

            # 5. Context Compression
            final_context = ContextBuilder.build(ranked_docs)
            
            if not final_context:
                final_answer = "Hệ thống chưa có tài liệu về vấn đề này."
            else:
                # 6. Generate
                print("[*] GENERATOR: Đang tổng hợp kết quả...")
                final_answer = self.generator.generate(query, final_context)

        # THÊM MỚI: Lưu lịch sử sau khi có câu trả lời (giữ tối đa 3 lượt để tránh tràn token)
        self.memory.append({"user": query, "bot": final_answer})
        if len(self.memory) > 3:
            self.memory.pop(0)

        return final_answer
    
    def process_with_context(self, raw_query: str) -> tuple[str, str]:
        """Hàm tiện ích để trả về cả answer và context cho mục đích đánh giá."""
        query = clean_text(raw_query)
        history_str = self._get_formatted_history()

        analysis = self.analyzer.analyze(query, history_str)

        if analysis.intent == "general":
            final_answer = "Xin chào! Tôi là hệ thống AI nội bộ TechCorp. Tôi có thể giúp bạn tra cứu tài liệu gì hôm nay?"
            final_context = ""
        else:
            search_query = self.rewriter.rewrite(query, analysis, history_str)
            strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)
            raw_docs = self.retriever.search(search_query, strategy, fetch_k)
            ranked_docs = self.policy.apply_policy(search_query, raw_docs, analysis)
            final_context = ContextBuilder.build(ranked_docs)
            
            if not final_context:
                final_answer = "Hệ thống chưa có tài liệu về vấn đề này."
            else:
                final_answer = self.generator.generate(query, final_context)

        self.memory.append({"user": query, "bot": final_answer})
        if len(self.memory) > 3:
            self.memory.pop(0)

        return final_answer, final_context
    
    def clear_memory(self):
        
        self.memory = []
# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    print("\n" + "#"*60)
    print("🚀 TECHCORP DECISION-DRIVEN RAG (PRODUCTION LEVEL)")
    print("#"*60)
    
    app = ProductionRAG()

    while True:
        user_input = input("\n👤 User: ")
        if user_input.lower() in ["exit", "q", "quit"]: break
        try:
            result = app.process(user_input)
            print(f"\n🤖 Bot:\n{result}")
        except Exception as e:
            print(f"\n❌ [LỖI HỆ THỐNG]: {e}")