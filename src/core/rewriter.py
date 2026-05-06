import re
import logging
from langsmith import traceable
from src.schemas import QueryAnalysis
from config.settings import settings

logger = logging.getLogger(__name__)


class QueryRewriter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def _has_entity_mismatch(self, query: str, entities: list[str]) -> bool:
       
        if not entities:
            return False
        query_lower = query.lower()
        missing = sum(1 for e in entities if e.lower() not in query_lower)
        return missing > len(entities) / 2

    def _is_over_rewritten(self, original: str, rewritten: str) -> bool:
      
        return len(rewritten) > len(original) * 2.5

    def _is_scope_narrowed(self, original: str, rewritten: str) -> bool:
        """
        True nếu rewrite tự thêm mệnh đề giới hạn/mục đích không có trong câu gốc.

        Vấn đề gốc: câu hỏi chung "phần mềm bảo mật nào" bị rewrite thành
        "phần mềm bảo mật nào để ngăn chặn email Phishing" → Qdrant ưu tiên
        document về phishing, bỏ sót các phần mềm khác (BitLocker/FileVault).

        Logic: tìm connector thu hẹp ("để", "nhằm", "cho mục đích") mà
        KHÔNG có trong câu gốc nhưng xuất hiện trong câu rewrite.
        """
        narrowing_patterns = [
            r'\bđể\s+\w',        # "để ngăn chặn", "để xử lý"
            r'\bnhằm\b',         # "nhằm mục đích"
            r'\bcho mục đích\b',
            r'\btrong trường hợp\b',
            r'\bliên quan đến\b',
            r'\bvề vấn đề\b',
        ]
        original_lower = original.lower()
        rewritten_lower = rewritten.lower()
        for pattern in narrowing_patterns:
            if not re.search(pattern, original_lower) and re.search(pattern, rewritten_lower):
                return True
        return False

    @staticmethod
    def _strip_preamble(text: str) -> str:
        """
        Loại bỏ phần mở đầu mà LLM đôi khi thêm vào trước câu hỏi thực.

        Xử lý 2 dạng:
        1. Inline preamble: "Câu hỏi đã viết lại: <actual query>"
           → LLM thêm label trên cùng một dòng, không có \\n\\n.
        2. Block preamble:  "Câu hỏi tối ưu:\\n\\n<actual query>"
           → LLM tách label và query bằng 2 dòng trắng.

        Cả hai đều làm nhiễu dense embedding và BM25 sparse → retrieve sai.
        """
        text = text.strip()

        # ── Dạng 1: Inline preamble ("Label: actual query") ──────────────────
        # Chỉ strip khi prefix khớp với một trong các label LLM hay dùng.
        _INLINE_LABELS = [
            "câu hỏi đã viết lại",
            "câu hỏi viết lại",
            "câu hỏi tối ưu",
            "câu hỏi sau khi",
            "câu hỏi được viết lại",
            "câu hỏi đã được viết lại",
            "query tối ưu",
            "kết quả viết lại",
            "rewritten query",
        ]
        text_lower = text.lower()
        for label in _INLINE_LABELS:
            if text_lower.startswith(label):
                colon_pos = text.find(":")
                if colon_pos > 0:
                    candidate = text[colon_pos + 1:].strip().strip('"\'\u201c\u201d\u2018\u2019')
                    if candidate:
                        return candidate

        # ── Dạng 2: Block preamble ("Preamble:\\n\\n<actual query>") ─────────
        if "\n\n" in text:
            parts = text.split("\n\n", 1)
            # Chỉ strip nếu phần trước dấu \n\n là preamble ngắn (< 120 chars)
            # và có chứa dấu ":" — đặc trưng của "Câu hỏi...: "
            if len(parts[0]) < 120 and ":" in parts[0]:
                candidate = parts[1].strip().strip('"\'\u201c\u201d\u2018\u2019')
                if candidate:
                    return candidate

        # Fallback: chỉ strip dấu nháy bao quanh nếu có
        return text.strip('"\'\u201c\u201d\u2018\u2019')

    @traceable(run_type="chain", name="Query_Rewrite_v3")
    def rewrite(self, query: str, analysis: QueryAnalysis, history: str = "") -> str:
        """
        Chỉ rewrite khi thực sự cần:
        - complexity cao (>= 0.58) → câu phức tạp thật sự
        - ambiguity cao (>= 0.4) → câu thực sự mơ hồ
        - entity mismatch THỰC SỰ (hơn nửa entities thiếu)
        """
        needs_rewrite = (
            analysis.complexity_score >= 0.58       
            or analysis.ambiguity_score >= 0.4     
            or self._has_entity_mismatch(query, analysis.entities)
        )
        if not needs_rewrite:
            return query

        prompt = f"""Bạn là Expert Search Engineer tại TechCorp. Nhiệm vụ: Viết lại câu hỏi để tối ưu Vector Search.

NGUYÊN TẮC:
1. GIỮ NGUYÊN thuật ngữ (Docker, VPN, Jira, AD account...).
2. THAY THẾ đại từ ("nó", "vấn đề đó") bằng thực thể gốc từ LỊCH SỬ.
3. DÙNG từ chuyên môn chính xác (VD: "lấy" -> "cấp phát").
4. TUYỆT ĐỐI KHÔNG thêm thông tin mới hoặc thu hẹp phạm vi ("để ngăn chặn X").
5. NGẮN GỌN, súc tích, tập trung vào keywords.

LỊCH SỬ:
{history}

CÂU HỎI GỐC: {query}
TRẢ VỀ CÂU HỎI TỐI ƯU:"""

        response = self.llm.chat.completions.create(
            model=settings.UTILITY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,    
        )
        raw_output = response.choices[0].message.content.strip()

        # Strip preamble TRƯỚC khi kiểm tra over-rewrite và log
        rewritten = self._strip_preamble(raw_output)

        if self._is_over_rewritten(query, rewritten):
            logger.info(f"  [Rewriter] '{query}' → SKIP (over-rewritten, fallback to original)")
            return query

        if self._is_scope_narrowed(query, rewritten):
            logger.info(f"  [Rewriter] '{query}' → SKIP (scope narrowed, fallback to original)")
            return query

        logger.info(f"  [Rewriter] '{query}' → '{rewritten}'")
        return rewritten