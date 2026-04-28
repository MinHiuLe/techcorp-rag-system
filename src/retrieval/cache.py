import numpy as np
import json
import os
from langsmith import traceable


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

    def add(self, query: str, query_embedding: list, answer: str, has_context: bool = True):
        # Skip if no context
        if not has_context:
            return

        # Normalize answer
        normalized_answer = answer.strip().lower()
        
        # Comprehensive list of "no answer" phrases
        no_answer_phrases = [
            "hệ thống chưa có tài liệu",
            "không có tài liệu",
            "không có thông tin", 
            "không tìm thấy",
            "không đủ thông tin",
            "no information",
            "not found"
        ]

        # Check if answer contains any "no answer" phrase
        for phrase in no_answer_phrases:
            if phrase in normalized_answer:
                print(f"[CACHE] Skipped - answer contains: '{phrase}'")
                return

        # Valid answer - save to cache
        self.cache_data.append({
            "query": query,
            "embedding": query_embedding,
            "answer": answer,
            "has_answer": True
        })

        self._save_cache()