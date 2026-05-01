"""
resource_profile.py — Centralized Resource-Tier Dispatcher (FINAL)

Design goals:
- Stable routing (không phụ thuộc LLM runtime)
- Không làm loãng context khi multi-topic
- Scale tài nguyên theo độ khó + số topic
- Tránh over-optimization gây mất recall

Tier mapping:
  FAST     complexity < 0.30
  STANDARD complexity < 0.65
  FULL     complexity ≥ 0.65
"""

from dataclasses import dataclass
from typing import Literal

Tier = Literal["FAST", "STANDARD", "FULL"]


@dataclass(frozen=True)
class ResourceProfile:
    tier: Tier
    complexity: float

    # ── Generator ───────────────────────────────────────
    max_output_tokens: int
    prompt_tier: Tier

    # ── Context Builder ─────────────────────────────────
    max_context_chars: int
    per_chunk_min_chars: int

    # ── Reranker ────────────────────────────────────────
    rerank_top_k: int

    # ── Rewriter ────────────────────────────────────────
    skip_rewrite: bool


    # ────────────────────────────────────────────────────
    # FACTORY
    # ────────────────────────────────────────────────────
    @classmethod
    def from_complexity(cls, complexity: float, n_topics: int = 1) -> "ResourceProfile":

        # ────────────────────────────────────────────────
        # FAST — single fact
        # ────────────────────────────────────────────────
        if complexity < 0.30:
            return cls(
                tier="FAST",
                complexity=complexity,

                max_output_tokens=280,
                prompt_tier="FAST",

                max_context_chars=1_200,
                per_chunk_min_chars=250,

                rerank_top_k=min(2 * n_topics, 4),

                skip_rewrite=True,
            )

        # ────────────────────────────────────────────────
        # STANDARD — 1 topic, vài bước
        # ────────────────────────────────────────────────
        elif complexity < 0.65:
            return cls(
                tier="STANDARD",
                complexity=complexity,

                max_output_tokens=450,
                prompt_tier="STANDARD",

                max_context_chars=2_800,
                per_chunk_min_chars=280,

                rerank_top_k=min(3 * n_topics, 6),

                skip_rewrite=False,
            )

        # ────────────────────────────────────────────────
        # FULL — multi-topic / complex reasoning
        # ────────────────────────────────────────────────
        else:
            if n_topics == 1:
                ctx = 5200
            elif n_topics == 2:
                ctx = 5200   
            else:
                ctx = min(1500 * n_topics, 5200)

            max_tokens = min(500 + 150 * n_topics, 900)

            rerank_k = min(3 * n_topics + 1, 7)

            return cls(
                tier="FULL",
                complexity=complexity,

                max_output_tokens=max_tokens,
                prompt_tier="FULL",

                max_context_chars=ctx,
                per_chunk_min_chars=300,

                rerank_top_k=rerank_k,

                skip_rewrite=False,
            )
    def log_summary(self) -> str:
        return (
            f"[Profile] tier={self.tier} | "
            f"ctx≤{self.max_context_chars}c | "
            f"out≤{self.max_output_tokens}tok | "
            f"top_k={self.rerank_top_k} | "
            f"skip_rewrite={self.skip_rewrite}"
        )