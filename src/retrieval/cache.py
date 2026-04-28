import numpy as np
import json
import os
from langsmith import traceable

NO_ANSWER_PHRASES = [
    "hệ thống chưa có tài liệu",
    "không có tài liệu",
    "không có thông tin",
    "không tìm thấy",
    "không đủ thông tin",
    "no information",
    "not found",
]

class SemanticCache:
    def __init__(self, threshold=0.90):
        self.threshold  = threshold
        self.cache_file = "storage/semantic_cache.json"
        self.cache_data = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache_data, f, ensure_ascii=False, indent=2)

    def cosine_similarity(self, vec1, vec2):
        v1, v2 = np.array(vec1), np.array(vec2)
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    def clear(self):
        self.cache_data = []
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
            print(f"  [Cache] Cleared in-memory + disk: {self.cache_file}")

    @traceable(run_type="tool", name="Semantic_Cache_Check")
    def check(self, query_embedding: list) -> str | None:
        if not self.cache_data:
            return None

        best_score  = 0
        best_answer = None

        for item in self.cache_data:
            score = self.cosine_similarity(query_embedding, item["embedding"])
            if score > best_score:
                best_score  = score
                best_answer = item["answer"]

        if best_score >= self.threshold:
            print(f"  ⚡ [Cache HIT] Khớp {best_score*100:.1f}% với một câu hỏi cũ!")
            return best_answer

        return None

    def add(self, query: str, query_embedding: list, answer: str, context: str):
        # 1. Check context
        if not context or not context.strip():
            return

        normalized = answer.strip().lower()
        for phrase in NO_ANSWER_PHRASES:
            if phrase in normalized:
                print(f"  [Cache] Skipped — answer contains: '{phrase}'")
                return
 
        self.cache_data.append({
            "query"    : query,
            "embedding": query_embedding,
            "answer"   : answer,
        })
        self._save_cache()
        print(f"  [Cache] Saved — '{query[:50]}...'")
