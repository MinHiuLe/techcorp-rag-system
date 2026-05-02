import json
import re
from pydantic import ValidationError
from src.schemas import QueryAnalysis
from config.settings import settings


class QueryAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client

    # ═══════════════════════════════════════════════════════
    # TẬP TỪ KHÓA PHÂN LOẠI
    # ═══════════════════════════════════════════════════════
    _PROCEDURE_KEYWORDS = [
        "cần làm gì", "phải làm gì", "các bước", "quy trình",
        "hướng dẫn", "xử lý như thế nào", "làm thế nào", "cách xử lý",
        "phải làm sao", "cần thực hiện", "giải quyết", "ngay sau đó"
    ]

    _CONDITION_KEYWORDS = [
        "nếu", "trong trường hợp", "khi mà", "miễn là",
        "giả sử", "trong tình huống", "trước khi"
    ]

    _IMPACT_KEYWORDS = [
        "ảnh hưởng", "tác động", "liên quan đến", "dẫn đến"
    ]

    _PROCESS_CONTEXT_KEYWORDS = [
        "giai đoạn", "tiến độ", "quy trình", "workflow",
        "stage", "phê duyệt", "đánh giá", "chậm", "deadline"
    ]

    # MỚI: Các từ khóa đặc thù TechCorp — nếu xuất hiện, bắt buộc technical
    _TECHNICAL_KEYWORDS = [
        "hạn mức", "mực in", "nghỉ phép", "lương", "bảo hiểm",
        "docker", "vpn", "laptop", "hợp đồng", "idp", "kpi",
        "onboarding", "techcorp", "ad", "mfa", "jira", "github",
        "bhxh", "phép năm", "thử việc", "đánh giá", "cải thiện",
        "anyconnect", "cisco", "qdrant", "server", "port",
        "thời hạn", "trách nhiệm", "tần suất", "định kỳ", "điểm",
        "phê duyệt", "procurement", "legal", "phishing", "mật khẩu",
        "security", "ticket", "hotline", "giấy chứng nhận", "bệnh viện",
        "ốm", "lương tháng 13", "onboarding", "it", "ae", "vp of sales"
    ]

    def _is_simple_fact(self, query: str) -> bool:
        query_lower = query.lower()

        if any(pk in query_lower for pk in self._PROCEDURE_KEYWORDS):
            return False
        if any(ck in query_lower for ck in self._CONDITION_KEYWORDS):
            return False
        if any(ik in query_lower for ik in self._IMPACT_KEYWORDS):
            return False
        if query.count(".") + query.count(";") > 0 and len(query) > 60:
            return False
        if any(pck in query_lower for pck in self._PROCESS_CONTEXT_KEYWORDS):
            return False

        fact_keywords = [
            "ai", "bao nhiêu", "khi nào", "ở đâu", "link", "địa chỉ",
            "thời hạn", "hạn mức", "trách nhiệm", "port", "mấy",
            "bao lâu", "tần suất", "định kỳ", "điểm", "mực in",
            "có.*không", "có thay đổi không", "có được", "có cần", "có bắt buộc",
            "có phải", "đã thay đổi chưa", "còn không"
        ]
        has_fact_keyword = any(re.search(pattern, query_lower) for pattern in fact_keywords)
        if not has_fact_keyword:
            return False

        complex_patterns = [
            r"\b(và|cũng như|cùng với|vừa.*vừa|nếu.*thì|khi.*thì)\b",
            r",\s*(và|cũng như)",
            r"\b(đồng thời|ngoài ra|hơn nữa)\b",
            r"\b(ảnh hưởng|tác động|liên quan đến)\b"
        ]
        if any(re.search(pattern, query_lower) for pattern in complex_patterns):
            return False

        if len(query) > 110:
            return False

        return True

    def _has_technical_keyword(self, query: str) -> bool:
        """True nếu query chứa từ khóa đặc thù của tài liệu nội bộ TechCorp."""
        query_lower = query.lower()
        return any(tk in query_lower for tk in self._TECHNICAL_KEYWORDS)

    def analyze(self, query: str, history: str = "") -> QueryAnalysis:
        history_section = (
            f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{history}\n"
            if history and history != "Không có."
            else ""
        )

        prompt = f"""Phân tích câu hỏi HIỆN TẠI và trả về JSON với 4 trường sau:

1. "intent": "technical" hoặc "general".

   RULE CỨNG CHO "general" — CHỈ áp dụng KHI VÀ CHỈ KHI câu là chào hỏi XÃ GIAO THUẦN TÚY:
   ✅ "general": "hello", "chào bạn", "hi", "bạn là ai?", "cảm ơn nhé", "tạm biệt"
   ❌ KHÔNG "general" — BẮT BUỘC "technical" với MỌI trường hợp dưới đây:
      • Câu kể tình huống cá nhân: "mình bị...", "tôi đang gặp...", "máy tôi..."
      • Câu than phiền / chia sẻ: "công ty đánh giá mình...", "mình lo lắng..."
      • Câu chứa BẤT KỲ từ nghiệp vụ nào: đánh giá, cải thiện, nghỉ phép, lương,
        bảo hiểm, Docker, VPN, laptop, hợp đồng, IDP, KPI, onboarding,
        hạn mức, mực in, điểm, phép năm, thử việc, BHXH, Jira, GitHub,
        MFA, AD, TechCorp, AnyConnect, Qdrant, ...
      • Câu hỏi về quy trình / chính sách dù được diễn đạt dạng kể lể.
   → Nguyên tắc: nếu câu có THỂ liên quan đến tài liệu nội bộ TechCorp, LUÔN dùng "technical".

2. "complexity_score": float 0.0–1.0.
   - 0.0–0.25: câu hỏi đơn giản, hỏi về 1 THUỘC TÍNH DUY NHẤT.
   - 0.3–0.65: câu hỏi vừa, cần 1–2 tài liệu, hỏi về quy trình hoặc vài bước.
   - 0.65–1.0: câu hỏi phức tạp, cần tổng hợp nhiều tài liệu HOẶC có nhiều câu hỏi con.

   ══ RULE BẮT BUỘC CHO SINGLE-FACT LOOKUP ══
   - Câu hỏi chứa 1 dấu "?" VÀ hỏi 1 thuộc tính duy nhất
     → complexity_score ≤ 0.20.
   - Câu yes/no → complexity_score = 0.15.

   ✅ Ví dụ ĐÚNG (complexity thấp ≤ 0.20):
      "Địa chỉ server VPN TechCorp-AnyConnect là gì?"   → 0.15
      "Link tải Cisco AnyConnect ở đâu?"                → 0.15
      "Ai chịu trách nhiệm thay mực in?"                → 0.15
      "Hạn mức in mỗi tháng là bao nhiêu điểm?"         → 0.15
      "Port mặc định của Qdrant là bao nhiêu?"          → 0.15

   ✅ Ví dụ ĐÚNG (complexity cao ≥ 0.8):
      "Cách cài VPN và Docker trên laptop mới?"         → 0.85
      "Nghỉ phép và lương tháng 13 tính như thế nào?"  → 0.85

   ══ RULE BỔ SUNG ══
   - Câu KHÔNG có dấu "?" → complexity_score ≤ 0.65.
   - Tên sản phẩm dài KHÔNG làm tăng complexity.

3. "ambiguity_score": float 0.0–1.0.
   Cao khi dùng đại từ ("nó", "cái đó") hoặc thiếu context.

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
            query_lower = query.lower()

            # ── Tính các flag dùng chung ──
            has_procedure = any(pk in query_lower for pk in self._PROCEDURE_KEYWORDS)
            has_condition = any(ck in query_lower for ck in self._CONDITION_KEYWORDS)
            has_impact    = any(ik in query_lower for ik in self._IMPACT_KEYWORDS)
            has_process_context = any(pck in query_lower for pck in self._PROCESS_CONTEXT_KEYWORDS)
            has_multiple_sentences = (query.count(".") + query.count(";")) > 0 and len(query) > 60

            # ═══════════════════════════════════════════════════════
            # MỚI: OVERRIDE INTENT — Nếu LLM trả general nhưng query
            # chứa từ khóa nghiệp vụ TechCorp → bắt buộc technical
            # ═══════════════════════════════════════════════════════
            if result.intent == "general" and self._has_technical_keyword(query):
                print(f"  [Analyzer] Technical keyword detected → force intent 'technical' (was 'general')")
                result = QueryAnalysis(
                    intent="technical",
                    complexity_score=result.complexity_score,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 1: OVERRIDE _is_simple_fact
            # ═══════════════════════════════════════════════════════
            if self._is_simple_fact(query):
                forced = 0.15

                # Câu "Ai/Bộ phận nào...khi..." có điều kiện
                if " khi " in query_lower and len(query) > 45:
                    forced = 0.35
                    print(f"  [Analyzer] Fact with 'khi' condition → force {forced} (was {result.complexity_score:.2f})")
                else:
                    print(f"  [Analyzer] Simple fact override → force 0.15 (was {result.complexity_score:.2f})")

                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=forced,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )
                return result

            # ═══════════════════════════════════════════════════════
            # PHẦN 2: SINGLE-? FACT LOOKUP
            # ═══════════════════════════════════════════════════════
            single_fact_patterns = [
                r"^ai\s+",
                r"^bộ phận nào\s+",
                r"^(có.*không)$",
                r"(địa chỉ|link|port|hạn mức|thời hạn|bao lâu|tần suất|mấy|bao nhiêu)"
            ]

            if query.count("?") == 1:
                is_single_fact = any(re.search(p, query_lower) for p in single_fact_patterns)
                has_conjunction = re.search(r"\b(và|cũng như|cùng với|vừa.*vừa)\b", query_lower)

                if (is_single_fact
                    and not has_conjunction
                    and not has_procedure
                    and not has_condition
                    and not has_impact
                    and not has_process_context
                    and not has_multiple_sentences
                    and result.complexity_score > 0.25):

                    clamped = 0.20
                    print(f"  [Analyzer] Single-fact lookup → clamp {result.complexity_score:.2f} → {clamped:.2f}")
                    result = QueryAnalysis(
                        intent=result.intent,
                        complexity_score=clamped,
                        ambiguity_score=result.ambiguity_score,
                        entities=result.entities,
                    )

                elif (is_single_fact
                      and not has_conjunction
                      and has_process_context
                      and not has_condition
                      and result.complexity_score > 0.40):

                    clamped = 0.35
                    print(f"  [Analyzer] Single-fact + process context → clamp {result.complexity_score:.2f} → {clamped:.2f}")
                    result = QueryAnalysis(
                        intent=result.intent,
                        complexity_score=clamped,
                        ambiguity_score=result.ambiguity_score,
                        entities=result.entities,
                    )

            # ═══════════════════════════════════════════════════════
            # PHẦN 3: CLAMP MAX CHO SINGLE-?
            # Ceiling nâng lên 0.65 để single-? queries thực sự phức tạp
            # (list queries, multi-aspect, conditional) vẫn vào FULL tier.
            # Trước: cap 0.55 → luôn STANDARD, bỏ sót khi answer là list.
            # ═══════════════════════════════════════════════════════
            if query.count("?") == 1 and result.complexity_score > 0.65:
                old = result.complexity_score
                if has_process_context or has_condition:
                    clamped = min(old, 0.75)
                else:
                    clamped = 0.65

                print(f"  [Analyzer] Single-? max clamp → {old:.2f} -> {clamped:.2f}")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=clamped,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 4: MULTI-? → tối thiểu 0.7
            # ═══════════════════════════════════════════════════════
            if query.count("?") >= 2 and result.complexity_score < 0.7:
                print(f"  [Analyzer] Multi-? → raise {result.complexity_score:.2f} → 0.70")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.70,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 5: KHÔNG DẤU ? → max 0.65
            # ═══════════════════════════════════════════════════════
            if "?" not in query and result.complexity_score > 0.65:
                print(f"  [Analyzer] No '?' → clamp 0.65")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.65,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 6: NÂNG TỐI THIỂU CHO PROCEDURE/CONDITION/IMPACT
            # ═══════════════════════════════════════════════════════
            if (has_procedure or has_condition or has_impact) and result.complexity_score < 0.35:
                print(f"  [Analyzer] Procedure/Condition/Impact → raise to 0.35")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.35,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 7: PROCESS CONTEXT → đảm bảo STANDARD tier
            # ═══════════════════════════════════════════════════════
            if has_process_context and result.complexity_score < 0.35:
                print(f"  [Analyzer] Process context → raise to 0.35")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.35,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 8: GUARD RAIL — Không cho xuống FAST tier
            # nếu câu có điều kiện hoặc ngữ cảnh phức tạp
            # ═══════════════════════════════════════════════════════
            if result.complexity_score < 0.30 and (has_condition or has_process_context):
                print(f"  [Analyzer] Guard rail: condition/process in FAST → raise to 0.30")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.30,
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