import json
import re
from pydantic import ValidationError
from src.schemas import QueryAnalysis
from config.settings import settings


class QueryAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client

    def _is_simple_fact(self, query: str) -> bool:
        """
        True nếu câu hỏi chỉ hỏi một thuộc tính đơn lẻ, một sự kiện có/không,
        không có cấu trúc phức tạp.
        """
        query_lower = query.lower()
        
        # Từ khoá fact đơn (bao gồm cả yes/no)
        fact_keywords = [
            "ai", "bao nhiêu", "khi nào", "ở đâu", "link", "địa chỉ",
            "thời hạn", "hạn mức", "trách nhiệm", "port", "số", "mấy",
            "bao lâu", "tần suất", "định kỳ", "trang", "điểm", "mực in",
            "có.*không", "có thay đổi không", "có được", "có cần", "có bắt buộc",
            "có phải", "đã thay đổi chưa", "còn không"
        ]
        has_fact_keyword = any(re.search(pattern, query_lower) for pattern in fact_keywords)
        if not has_fact_keyword:
            return False

        # Dấu hiệu câu phức tạp (có từ nối, điều kiện, liệt kê)
        complex_patterns = [
            r"\b(và|cũng như|cùng với|vừa.*vừa|nếu.*thì|khi.*thì)\b",
            r",\s*(và|cũng như)",          # dấu phẩy liệt kê
            r"\b(đồng thời|ngoài ra|hơn nữa)\b",
            r"\b(ảnh hưởng|tác động|liên quan đến)\b"
        ]
        if any(re.search(pattern, query_lower) for pattern in complex_patterns):
            return False

        # Câu quá dài (>110 ký tự) có thể vẫn là simple fact nhưng hiếm
        if len(query) > 110:
            return False

        return True

    def analyze(self, query: str, history: str = "") -> QueryAnalysis:
        history_section = (
            f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{history}\n"
            if history and history != "Không có."
            else ""
        )

        # Prompt kết hợp rule chặt từ phiên bản thứ hai, nhưng giữ cấu trúc chi tiết
        prompt = f"""Phân tích câu hỏi HIỆN TẠI và trả về JSON với 4 trường sau:

1. "intent": "technical" hoặc "general".

   RULE CỨNG CHO "general" — CHỈ áp dụng KHI VÀ CHỈ KHI câu là chào hỏi XÃ GIAO THUẦN TÚY:
   ✅ "general": "hello", "chào bạn", "hi", "bạn là ai?", "cảm ơn nhé"
   ❌ KHÔNG "general" — BẮT BUỘC "technical" với MỌI trường hợp dưới đây:
      • Câu kể tình huống cá nhân: "mình bị...", "tôi đang gặp...", "máy tôi..."
      • Câu than phiền / chia sẻ: "công ty đánh giá mình...", "mình lo lắng..."
      • Câu chứa BẤT KỲ từ nghiệp vụ nào: đánh giá, cải thiện, nghỉ phép, lương,
        bảo hiểm, Docker, VPN, laptop, hợp đồng, IDP, KPI, onboarding, ...
      • Câu hỏi về quy trình / chính sách dù được diễn đạt dạng kể lể.
   → Nguyên tắc: nếu câu có THỂ liên quan đến tài liệu nội bộ TechCorp, LUÔN dùng "technical".

2. "complexity_score": float 0.0–1.0.
   - 0.0–0.25: câu hỏi đơn giản, hỏi về 1 THUỘC TÍNH DUY NHẤT (địa chỉ, link, tên, số, thời hạn, ai chịu trách nhiệm, bộ phận nào, bao nhiêu, có/không).
   - 0.3–0.65: câu hỏi vừa, cần 1–2 tài liệu, hỏi về quy trình hoặc vài bước.
   - 0.65–1.0: câu hỏi phức tạp, cần tổng hợp nhiều tài liệu HOẶC có nhiều câu hỏi con khác nhau.

   ══ RULE BẮT BUỘC CHO SINGLE-FACT LOOKUP ══
   - Câu hỏi chứa 1 dấu "?" VÀ hỏi 1 thuộc tính duy nhất (địa chỉ, link, tên, port, số, ngày, ai, bộ phận nào, hạn mức)
     → complexity_score ≤ 0.20, NGAY CẢ KHI tên kỹ thuật dài hoặc phức tạp.
   - Câu hỏi dạng "Ai chịu trách nhiệm X?", "Bộ phận nào quản lý Y?", "Ai xử lý Z?"
     → complexity_score = 0.15 (vì chỉ 1 fact: tên người/bộ phận).
   - Câu yes/no ("có được không?", "có bắt buộc không?") → complexity_score = 0.15.

   ✅ Ví dụ ĐÚNG (complexity thấp ≤ 0.20):
      "Địa chỉ server VPN TechCorp-AnyConnect là gì?"   → 0.15
      "Link tải Cisco AnyConnect ở đâu?"                → 0.15
      "Ai chịu trách nhiệm thay mực in?"                → 0.15
      "Bộ phận nào quản lý onboarding IT?"              → 0.15
      "Thời hạn thử việc tại TechCorp là bao lâu?"      → 0.20
      "Port mặc định của Qdrant là bao nhiêu?"          → 0.15
      "Hạn mức in mỗi tháng là bao nhiêu điểm?"         → 0.15
      "Có được dùng Docker image latest trong production không?" → 0.15

   ✅ Ví dụ ĐÚNG (complexity cao ≥ 0.8):
      "Cách cài VPN và Docker trên laptop mới?"         → 0.85 (2 chủ đề khác nhau)
      "Nghỉ phép và lương tháng 13 tính như thế nào?"  → 0.85 (2 chủ đề)
      "Giải thích toàn bộ quy trình onboarding IT?"    → 0.70 (nhiều bước, nhiều doc)
      "Nếu nhân viên vừa nghỉ ốm vừa bị đánh giá kém thì sao?" → 0.80 (multi-hop)

   ══ RULE BỔ SUNG ══
   - Câu KHÔNG có dấu "?" → câu kể / trình bày tình huống → complexity_score ≤ 0.65.
   - Tên sản phẩm dài (TechCorp-AnyConnect, Docker) KHÔNG làm tăng complexity.

3. "ambiguity_score": float 0.0–1.0.
   Cao khi dùng đại từ ("nó", "cái đó", "vấn đề này") hoặc thiếu context.
   Thấp khi câu hỏi có tên cụ thể, rõ ràng.

4. "entities": mảng string — các từ khóa kỹ thuật quan trọng.
   Nếu query dùng đại từ, lấy entity từ lịch sử hội thoại.

LƯU Ý CUỐI: Chỉ trả về JSON, không giải thích thêm.

{history_section}CÂU HỎI HIỆN TẠI: {query}"""

        response = self.llm.chat.completions.create(
            model=settings.UTILITY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response.choices[0].message.content)
            result = QueryAnalysis(**data)

            # ───── PHẦN 1: OVERRIDE BẰNG RULE _is_simple_fact (ưu tiên cao nhất) ─────
            if self._is_simple_fact(query):
                forced = 0.15
                if result.complexity_score != forced:
                    print(f"  [Analyzer] Simple fact override → force complexity 0.15 (was {result.complexity_score:.2f})")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=forced,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )
                return result

            # ───── PHẦN 2: SINGLE-? FACT LOOKUP (dựa trên từ khóa ai/bao nhiêu/...) ─────
            # Bổ sung theo rule của phiên bản thứ hai: các câu hỏi 1 fact đặc biệt
            single_fact_patterns = [
                r"^ai\s+",                           # "Ai chịu trách nhiệm..."
                r"^bộ phận nào\s+",                  # "Bộ phận nào quản lý..."
                r"^(có.*không)$",                    # yes/no
                r"(địa chỉ|link|port|số|hạn mức|thời hạn|bao lâu|tần suất|mấy|bao nhiêu)"
            ]
            if query.count("?") == 1:
                is_single_fact = any(re.search(p, query.lower()) for p in single_fact_patterns)
                # Thêm điều kiện: không có từ nối, không có dấu phẩy liệt kê
                has_conjunction = re.search(r"\b(và|cũng như|cùng với|vừa.*vừa)\b", query.lower())
                if is_single_fact and not has_conjunction and result.complexity_score > 0.25:
                    clamped = 0.20
                    print(f"  [Analyzer] Single-fact lookup → clamp complexity {result.complexity_score:.2f} → {clamped:.2f}")
                    result = QueryAnalysis(
                        intent=result.intent,
                        complexity_score=clamped,
                        ambiguity_score=result.ambiguity_score,
                        entities=result.entities,
                    )

            # ───── PHẦN 3: CLAMP CỨNG CHO SINGLE-? (không cho > 0.55) ─────
            if query.count("?") == 1 and result.complexity_score > 0.55:
                old = result.complexity_score
                clamped = 0.55
                print(f"  [Analyzer] Single-? max 0.55 → clamp {old:.2f} -> {clamped:.2f}")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=clamped,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ───── PHẦN 4: MULTI-? → tối thiểu 0.7 ─────
            if query.count("?") >= 2 and result.complexity_score < 0.7:
                print(f"  [Analyzer] Multi-? → nâng complexity {result.complexity_score:.2f} → 0.70")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.70,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ───── PHẦN 5: KHÔNG DẤU ? → max 0.65 ─────
            if "?" not in query and result.complexity_score > 0.65:
                print(f"  [Analyzer] No '?' → clamp xuống 0.65")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.65,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            return result

        except (ValidationError, Exception) as e:
            print(f"  [Analyzer] Fallback do lỗi: {e}")
            return QueryAnalysis(
                intent="technical",
                complexity_score=0.3,
                ambiguity_score=0.5,
                entities=[],
            )