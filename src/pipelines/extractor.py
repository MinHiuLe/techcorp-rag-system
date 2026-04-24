import re
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any

from src.schemas import DocumentMetadata, Provenance

logger = logging.getLogger(__name__)

class MetadataExtractor:
    def __init__(self):
        self.category_rules = {
            "IT": {r'(server|database|deploy|api|source code|git)': 3, r'(code|phần mềm|cài đặt|vpn|wifi|thiết bị|bảo mật|máy in|jira|laptop)': 1},
            "HR": {r'(hợp đồng lao động|nghỉ phép năm|performance review|idp)': 3, r'(nhân sự|lương|bảo hiểm|tuyển dụng|leave request|onboarding)': 1},
            "Sales": {r'(chốt deal|doanh thu quý|enterprise deals)': 3, r'(khách hàng|chiến dịch|kpi|sale|marketing|pipeline)': 1}
        }
        self.doctype_rules = {
            "Policy": { r'(quy định|quy trình|chính sách|policy|compliance|nội quy)': 2 },
            "Contract": { r'(hợp đồng|thỏa thuận|cam kết|contract|nda|biên bản)': 2 },
            "Tutorial": { r'(hướng dẫn|cách cài đặt|step|guide|tutorial|cẩm nang)': 2 }
        }
        self.security_mapping = {"Contract": "Confidential", "Policy": "Internal", "Tutorial": "Public", "Document": "Internal"}

    def _extract_tier1_path(self, file_key: str) -> Dict[str, str]:
        meta = {}
        path_upper = file_key.upper()
        file_lower = file_key.lower()

        for cat in ["IT", "HR", "SALES"]:
            if f"{cat}/" in path_upper or f"{cat.lower()}_" in file_lower:
                meta["category"] = cat.capitalize()
                break
        
        year_match = re.search(r'(202\d)', file_key)
        if year_match: meta["updated_at"] = year_match.group(1)
        return meta

    def _extract_tier2_scoring(self, content: str) -> Dict[str, str]:
        meta = {}
        sample_text = content[:2000].lower()
        
        def calculate_score(rules_dict):
            scores = {}
            for target, patterns in rules_dict.items():
                score = sum(len(re.findall(p, sample_text)) * w for p, w in patterns.items())
                scores[target] = score
            return scores

        cat_scores = calculate_score(self.category_rules)
        best_cat = max(cat_scores, key=cat_scores.get)
        if cat_scores[best_cat] >= 3: meta["category"] = best_cat

        type_scores = calculate_score(self.doctype_rules)
        best_type = max(type_scores, key=type_scores.get)
        if type_scores[best_type] >= 2: meta["doc_type"] = best_type

        return meta

    def process(self, file_key: str, content: str) -> DocumentMetadata:
        doc_id = hashlib.md5(file_key.encode()).hexdigest()
        
        final_meta = {"document_id": doc_id, "source": file_key, "category": None, "doc_type": None, "updated_at": None}
        tier_used = "Default"

        # --- TẦNG 1 ---
        t1_meta = self._extract_tier1_path(file_key)
        if t1_meta.get("category"):
            final_meta.update(t1_meta)
            tier_used = "T1_Path"

        # --- TẦNG 2 ---
        if final_meta["category"] is None or final_meta["doc_type"] is None:
            t2_meta = self._extract_tier2_scoring(content)
            if final_meta["category"] is None and t2_meta.get("category"):
                final_meta["category"] = t2_meta["category"]
                tier_used = "T2_Scoring"
            if final_meta["doc_type"] is None and t2_meta.get("doc_type"):
                final_meta["doc_type"] = t2_meta["doc_type"]

        # --- DỌN DẸP & ÁP DỤNG RULE ---
        final_cat = final_meta.get("category") or "General"
        final_type = final_meta.get("doc_type") or "Document"
        security = self.security_mapping.get(final_type, "Internal")

        logger.info(f"[{file_key}] -> Cat: {final_cat} (via {tier_used}) | Type: {final_type}")

        return DocumentMetadata(
            document_id=final_meta["document_id"],
            source=final_meta["source"],
            category=final_cat.capitalize(),
            doc_type=final_type.capitalize(),
            security_level=security,
            updated_at=final_meta["updated_at"],
            provenance=Provenance(tier=tier_used)
        )