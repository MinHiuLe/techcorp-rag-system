class ContextBuilder:

    @staticmethod
    def _get_max_context(complexity: float) -> int:
        """
        Dynamic context budget (chars) theo complexity.

        12,000 chars cũ ≈ 3,000 tokens — quá lớn cho mọi trường hợp.
        Map mới:
          < 0.3  → 2,000 chars  (~500  input tokens)  — 1 fact đơn giản
          < 0.65 → 3,500 chars  (~875  input tokens)  — vài điểm trình bày
          ≥ 0.65 → 5,500 chars  (~1,375 input tokens) — multi-topic, bảng biểu

        Ceiling 5,500 vẫn đảm bảo bảng Markdown hoàn chỉnh không bị cắt giữa chừng.
        """
        if complexity < 0.3:
            return 2_000
        elif complexity < 0.65:
            return 3_500
        else:
            return 5_500

    @staticmethod
    def _truncate_chunk(text: str, limit: int) -> str:
        """
        Cắt chunk tại newline gần nhất trong giới hạn, tránh cắt giữa câu.
        Nếu chunk là bảng Markdown (có '|'), giữ nguyên toàn bộ bảng
        miễn là nằm trong limit × 1.5 (bảng cần được bảo toàn cấu trúc).
        """
        if len(text) <= limit:
            return text

        # Ưu tiên giữ nguyên bảng Markdown
        if '|' in text and len(text) <= int(limit * 1.5):
            return text

        truncated = text[:limit]
        last_nl = truncated.rfind('\n')
        # Chỉ cắt tại newline nếu nó nằm ở nửa sau của đoạn cắt
        if last_nl > limit // 2:
            truncated = truncated[:last_nl]
        return truncated.rstrip() + "…"

    @staticmethod
    def build(documents: list, complexity: float = 0.5) -> str:
        if not documents:
            return ""

        # ── Dedup ────────────────────────────────────────────────────────────
        seen_texts = set()
        unique_docs = []
        for doc in documents:
            if doc['text'] not in seen_texts:
                seen_texts.add(doc['text'])
                unique_docs.append(doc)

        # ── Budget ───────────────────────────────────────────────────────────
        max_context_chars = ContextBuilder._get_max_context(complexity)

        # Per-chunk limit: fair share, tối thiểu 300 chars để không mất thông tin
        per_chunk_limit = max(300, max_context_chars // len(unique_docs))

        # ── Assemble ─────────────────────────────────────────────────────────
        context_parts = []
        current_length = 0

        for doc in unique_docs:
            text    = ContextBuilder._truncate_chunk(doc['text'], per_chunk_limit)
            snippet = f"[Nguồn: {doc['source']}]\n{text}\n---"

            if current_length + len(snippet) > max_context_chars:
                print(f"  [Builder] Budget ({max_context_chars} chars) đã đầy → dừng tại {len(context_parts)} chunks")
                break

            context_parts.append(snippet)
            current_length += len(snippet)

        print(
            f"  [Builder] {len(context_parts)}/{len(unique_docs)} chunks | "
            f"{current_length} chars | budget={max_context_chars} | per_chunk≤{per_chunk_limit}"
        )
        return "\n".join(context_parts)