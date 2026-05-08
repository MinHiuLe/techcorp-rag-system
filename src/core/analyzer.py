import json
import re
import logging
from pydantic import ValidationError
from langsmith import traceable
from src.schemas import QueryAnalysis
from src.utils.text_utils import extract_json
from config.settings import settings

logger = logging.getLogger(__name__)


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
        "ốm", "lương tháng 13", "onboarding", "it", "ae", "vp of sales",
        "thai sản", "xin nghỉ", "nghỉ thai sản", "nghỉ việc", "có thai", "vợ sinh", "nghỉ đẻ"
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

    @traceable(run_type="chain", name="Query_Analysis_v5")
    def analyze(self, query: str, history: str = "") -> QueryAnalysis:
        history_section = (
            f"LỊCH SỬ:\n{history}\n"
            if history and history != "Không có."
            else ""
        )

        prompt = f"""Bạn là Senior Analyzer tại TechCorp. Nhiệm vụ: Phân loại câu hỏi để tối ưu RAG.

1. "intent": 
   - "general": CHỈ khi chào hỏi/xã giao (hi, cảm ơn, bạn là ai).
   - "technical": BẮT BUỘC nếu liên quan đến: quy trình IT/HR, phần mềm (Docker, VPN, Jira), thiết bị, lương/thưởng, chính sách công ty.

2. "complexity_score" (0.0-1.0):
   - 0.1-0.2: Hỏi 1 sự kiện/con số (Địa chỉ server? Hạn mức in? Ai phụ trách?).
   - 0.3-0.6: Hỏi quy trình 1 chủ đề, điều kiện "Nếu...thì".
   - 0.7-1.0: Hỏi nhiều chủ đề cùng lúc, so sánh chính sách, tổng hợp dữ liệu.

3. "ambiguity_score": Cao nếu thiếu thông tin hoặc dùng "nó/vấn đề đó" mà lịch sử không giải thích được.

4. "entities": Danh sách các từ khóa kỹ thuật/quy trình quan trọng.

LƯU Ý: Trả về JSON thuần túy.

{history_section}CÂU HỎI: {query}"""

        response = self.llm.chat.completions.create(
            model=settings.UTILITY_MODEL, # [TỐI ƯU] Dùng Llama 8B qua Groq cho tốc độ tức thì
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        try:
            raw_content = response.choices[0].message.content
            json_str = extract_json(raw_content)
            data = json.loads(json_str)
            
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
                logger.info(f"  [Analyzer] Technical keyword detected → force intent 'technical' (was 'general')")
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
                    logger.info(f"  [Analyzer] Fact with 'khi' condition → force {forced} (was {result.complexity_score:.2f})")
                else:
                    logger.info(f"  [Analyzer] Simple fact override → force 0.15 (was {result.complexity_score:.2f})")

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
                    logger.info(f"  [Analyzer] Single-fact lookup → clamp {result.complexity_score:.2f} → {clamped:.2f}")
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
                    logger.info(f"  [Analyzer] Single-fact + process context → clamp {result.complexity_score:.2f} → {clamped:.2f}")
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
            # ═══════════════════════════════════════════════════════
            if query.count("?") == 1 and result.complexity_score > 0.65:
                old = result.complexity_score
                if has_process_context or has_condition:
                    clamped = min(old, 0.75)
                else:
                    clamped = 0.65

                logger.info(f"  [Analyzer] Single-? max clamp → {old:.2f} -> {clamped:.2f}")
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
                logger.info(f"  [Analyzer] Multi-? → raise {result.complexity_score:.2f} → 0.70")
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
                logger.info(f"  [Analyzer] No '?' → clamp 0.65")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.65,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 6: NÂNG TỐI THIỂU CHO CÁC KHÁI NIỆM QUAN TRỌNG
            # Consolidation of PROCEDURE/CONDITION/IMPACT/PROCESS
            # ═══════════════════════════════════════════════════════
            if (has_procedure or has_condition or has_impact or has_process_context) and result.complexity_score < 0.35:
                logger.info(f"  [Analyzer] Important concept detected → raise to 0.35")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.35,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            # ═══════════════════════════════════════════════════════
            # PHẦN 7: GUARD RAIL — Không cho xuống FAST tier
            # nếu câu có điều kiện hoặc ngữ cảnh phức tạp
            # ═══════════════════════════════════════════════════════
            if result.complexity_score < 0.30 and (has_condition or has_process_context):
                logger.info(f"  [Analyzer] Guard rail: condition/process in FAST → raise to 0.30")
                result = QueryAnalysis(
                    intent=result.intent,
                    complexity_score=0.30,
                    ambiguity_score=result.ambiguity_score,
                    entities=result.entities,
                )

            return result

        except (ValidationError, Exception) as e:
            logger.error(f"  [Analyzer] Fallback do lỗi: {e}")
            return QueryAnalysis(
                intent="technical",
                complexity_score=0.3,
                ambiguity_score=0.5,
                entities=[],
            )
   