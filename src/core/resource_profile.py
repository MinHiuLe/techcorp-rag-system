"""
resource_profile.py — Centralized Resource-Tier Dispatcher (v5.1)

Changes:
- Increase STANDARD max_output_tokens 450→650 for multi-claim answers
- Decrease STANDARD per_chunk_min_chars 280→200 to fit more chunks
- Increase FAST max_output_tokens 280→350 to avoid mid-sentence cutoff
"""

from dataclasses import dataclass
from typing import Literal

Tier = Literal["FAST", "STANDARD", "FULL"]


@dataclass(frozen=True)
class ResourceProfile:
    tier: Tier
    complexity: float

    max_output_tokens: int
    prompt_tier: Tier

    max_context_chars: int
    per_chunk_min_chars: int

    rerank_top_k: int
    skip_rewrite: bool

    @classmethod
    def from_complexity(cls, complexity: float, n_topics: int = 1) -> "ResourceProfile":

        # ── FAST: single fact, but allow 2 short claims ──
        if complexity < 0.30:
            return cls(
                tier="FAST",
                complexity=complexity,

                max_output_tokens=350,      # ↑ 280→350: đủ cho 2 ý ngắn
                prompt_tier="FAST",

                max_context_chars=1_800,
                per_chunk_min_chars=250,

                rerank_top_k=min(3 * n_topics, 5),
                skip_rewrite=True,
            )

        # ── STANDARD: multi-step, multi-claim answers ──
        elif complexity < 0.65:
            return cls(
                tier="STANDARD",
                complexity=complexity,

                max_output_tokens=650,      # ↑ 450→650: đủ cho 3–4 ý then chốt
                prompt_tier="STANDARD",

                max_context_chars=2_800,
                per_chunk_min_chars=200,    # ↓ 280→200: nhiều chunk hơn, đa dạng hơn

                rerank_top_k=min(3 * n_topics, 6),
                skip_rewrite=False,
            )

        # ── FULL: complex reasoning, multi-topic ──
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