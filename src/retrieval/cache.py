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
    # Câu chào hỏi mặc định (intent=general) — không được cache
    "xin chào! tôi là hệ thống",
    "tôi là hệ thống ai nội bộ",
    "xin chào! tôi là ai",
]


class SemanticCache:
    def __init__(self, threshold: float = 0.90):
        self.threshold  = threshold
        self.cache_file = "storage/semantic_cache.json"
        self.cache_data = self._load_cache()

    # ── Persistence ─────────────────────────────────────────────────────────────

    def _load_cache(self) -> list:
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_cache(self) -> None:
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache_data, f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        """Xóa cache in-memory + disk. Dùng trong eval mode."""
        self.cache_data = []
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
            print(f"  [Cache] Cleared in-memory + disk: {self.cache_file}")

    def validate_and_clean(self) -> None:
        """
        Scan toàn bộ cache, xóa các entry bị nhiễm độc (poisoned).

        Entry bị coi là poisoned nếu answer chứa bất kỳ NO_ANSWER_PHRASES nào.
        Gọi khi startup để tự động dọn dẹp cache từ version cũ.

        VD lỗi đã xảy ra: "mình bị công ty đánh giá..." bị classifier cũ
        phân loại nhầm là intent=general → cache lưu "Xin chào! Tôi là..."
        → mọi query tương tự sau đó đều nhận được câu chào sai.
        """
        original_len = len(self.cache_data)
        clean_data   = []

        for item in self.cache_data:
            normalized = item.get("answer", "").strip().lower()
            is_bad     = any(phrase in normalized for phrase in NO_ANSWER_PHRASES)
            if is_bad:
                print(f"  [Cache] 🧹 Removed poisoned entry: '{item.get('query', '')[:60]}...'")
            else:
                clean_data.append(item)

        removed = original_len - len(clean_data)
        if removed > 0:
            self.cache_data = clean_data
            self._save_cache()
            print(f"  [Cache] validate_and_clean: removed {removed} poisoned entries.")
        else:
            print(f"  [Cache] validate_and_clean: cache sạch ({original_len} entries OK).")

    # ── Similarity ───────────────────────────────────────────────────────────────

    @staticmethod
    def _cosine(vec1: list, vec2: list) -> float:
        v1, v2 = np.array(vec1), np.array(vec2)
        denom = np.linalg.norm(v1) * np.linalg.norm(v2)
        return float(np.dot(v1, v2) / denom) if denom > 0 else 0.0

    # ── Public API ───────────────────────────────────────────────────────────────

    @traceable(run_type="tool", name="Semantic_Cache_Check")
    def check(self, query_embedding: list) -> str | None:
        """Trả về cached answer nếu có HIT, None nếu MISS."""
        if not self.cache_data:
            return None

        best_score, best_answer = 0.0, None
        for item in self.cache_data:
            score = self._cosine(query_embedding, item["embedding"])
            if score > best_score:
                best_score, best_answer = score, item["answer"]

        if best_score >= self.threshold:
            print(f"  ⚡ [Cache HIT] Khớp {best_score * 100:.1f}% với câu hỏi cũ!")
            return best_answer

        return None

    def add(self, query: str, query_embedding: list, answer: str) -> None:
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