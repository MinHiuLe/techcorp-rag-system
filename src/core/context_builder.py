"""
context_builder.py — Profile-Aware Context Assembler

Nhận ResourceProfile thay vì complexity float thuần,
để tất cả budget đến từ single source of truth.

Backward-compat: build() vẫn nhận complexity=float nếu profile=None
(dùng khi gọi từ eval pipeline chưa update).
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from langsmith import traceable

if TYPE_CHECKING:
    from src.core.resource_profile import ResourceProfile


class ContextBuilder:

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    @traceable(run_type="chain", name="Context_Builder_v3")
    def build(
        documents: list,
        complexity: float = 0.5,      # legacy param — bị override nếu profile có
        profile: "ResourceProfile | None" = None,
    ) -> str:
        """
        Lắp ráp context string từ ranked documents.

        Ưu tiên dùng profile (từ ResourceProfile.from_complexity()).
        Fallback về legacy complexity float để eval pipeline không bị vỡ.
        """
        if not documents:
            return ""

        # ── Lấy budget từ profile hoặc tính lại nếu không có ─────────────────
        if profile is not None:
            max_context_chars = profile.max_context_chars
            per_chunk_min     = profile.per_chunk_min_chars
        else:
            max_context_chars = ContextBuilder._legacy_max_context(complexity)
            per_chunk_min     = 280

        # ── Dedup ──────────────────────────────────────────────────────────────
        seen_texts = set()
        unique_docs = []
        for doc in documents:
            if doc["text"] not in seen_texts:
                seen_texts.add(doc["text"])
                unique_docs.append(doc)

        # ── Per-chunk budget ───────────────────────────────────────────────────
        per_chunk_limit = max(per_chunk_min, max_context_chars // len(unique_docs))

        # ── Assemble ───────────────────────────────────────────────────────────
        context_parts  = []
        current_length = 0

        for doc in unique_docs:
            text    = ContextBuilder._truncate_chunk(doc["text"], per_chunk_limit)
            snippet = f"[Nguồn: {doc['source']}]\n{text}\n---"

            if current_length + len(snippet) > max_context_chars:
                print(
                    f"  [Builder] Budget ({max_context_chars}c) đầy "
                    f"→ dừng tại {len(context_parts)} chunks"
                )
                break

            context_parts.append(snippet)
            current_length += len(snippet)

        tier = profile.tier if profile else "legacy"
        print(
            f"  [Builder/{tier}] {len(context_parts)}/{len(unique_docs)} chunks "
            f"| {current_length}c | budget≤{max_context_chars}c "
            f"| per_chunk≤{per_chunk_limit}c"
        )
        return "\n".join(context_parts)

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _legacy_max_context(complexity: float) -> int:
        """Backward-compat với code chưa pass profile."""
        if complexity < 0.30:
            return 1_200
        elif complexity < 0.65:
            return 2_800
        else:
            return 5_200

    @staticmethod
    def _truncate_chunk(text: str, limit: int) -> str:
        """
        Cắt chunk tại newline gần nhất, tránh cắt giữa câu.

        Bảng Markdown — bảo toàn đặc biệt:
        - ≤ 2× limit → giữ nguyên toàn bộ bảng (bảng nhiều row, ~800-1000 chars)
        - > 2× limit → cắt tại row boundary để không mất dữ liệu ô
        """
        if len(text) <= limit:
            return text

        if "|" in text:
            if len(text) <= int(limit * 2.0):
                return text
            # Bảng quá lớn: cắt tại row boundary
            rows, result, chars = text.split("\n"), [], 0
            for row in rows:
                if chars + len(row) + 1 > limit and result:
                    break
                result.append(row)
                chars += len(row) + 1
            return "\n".join(result).rstrip()

        # Text thường: cắt tại newline nếu ở nửa sau
        truncated = text[:limit]
        last_nl   = truncated.rfind("\n")
        if last_nl > limit // 2:
            truncated = truncated[:last_nl]
        return truncated.rstrip() + "…"