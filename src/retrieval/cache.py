import numpy as np
import json
import os
from langsmith import traceable

class SemanticCache:
    def __init__(self, threshold=0.92):
        # Ngưỡng tương đồng: 0.92 là mức an toàn để tránh bot nhận diện sai ý
        self.threshold = threshold
        self.cache_file = "storage/semantic_cache.json"
        self.cache_data = self._load_cache()

    def _load_cache(self):
        """Tải dữ liệu cache từ ổ cứng nếu có."""
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_cache(self):
        """Lưu dữ liệu cache xuống ổ cứng."""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache_data, f, ensure_ascii=False, indent=2)

    def cosine_similarity(self, vec1, vec2):
        """Hàm tính khoảng cách Cosine giữa 2 vector."""
        v1, v2 = np.array(vec1), np.array(vec2)
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    
    @traceable(run_type="tool", name="Semantic_Cache_Check")
    def check(self, query_embedding: list) -> str:
        """Kiểm tra xem câu hỏi có nằm trong bộ nhớ đệm không."""
        if not self.cache_data: 
            return None

        best_score = 0
        best_answer = None
        
        for item in self.cache_data:
            score = self.cosine_similarity(query_embedding, item["embedding"])
            if score > best_score:
                best_score = score
                best_answer = item["answer"]

        if best_score >= self.threshold:
            print(f"  ⚡ [Cache HIT] Khớp {best_score*100:.1f}% với một câu hỏi cũ!")
            return best_answer

        return None

    def add(self, query: str, query_embedding: list, answer: str):
        # Không cache câu trả lời "không có tài liệu"
        if "chưa có tài liệu" in answer.lower():
            return
        self.cache_data.append({
            "query": query,
            "embedding": query_embedding,
            "answer": answer
        })
        self._save_cache()