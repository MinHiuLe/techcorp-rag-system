"""
gemini_rotator.py — Gemini API Key Rotator (Fixed v2)

Fixes so với v1:
  BUG 1: _rpm_guard dùng global _last_call → tất cả keys bị hit liên tiếp
          Fix: per-key last_call_at tracking trong _KeySlot
  BUG 2: max_attempts = slots*2 → RuntimeError thay vì chờ đúng cách
          Fix: _get_best_slot() luôn trả về slot, tự tính wait time

Env vars:
  GOOGLE_API_KEY=key1,key2,key3
  hoặc GOOGLE_API_KEY_1=..., GOOGLE_API_KEY_2=...
"""

from __future__ import annotations

import json
import os
import re
import time
import logging
from threading import Lock
from dataclasses import dataclass

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, GoogleAPIError, InternalServerError

logger = logging.getLogger(__name__)

def _extract_json(text: str) -> str:
    """Robust JSON extraction from LLM output (handles markdown, extra text)."""
    if not text:
        return ""
    text = text.strip()
    # Nếu wrapped trong ```json ... ```
    if text.startswith("```"):
        # Bỏ dòng đầu ```json
        lines = text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Tìm object JSON đầu tiên { ... }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return text



# Gemma 4 31B free: 15 RPM → 1 call/4s per key. Dùng 5s để có buffer.
PER_KEY_MIN_INTERVAL = 5.0   # giây tối thiểu giữa 2 calls trên cùng 1 key
COOLDOWN_SECONDS     = 65.0  # khi bị 429 (60s window + 5s buffer)


# ── Key Slot ──────────────────────────────────────────────────────────────────

@dataclass
class _KeySlot:
    api_key: str
    index: int
    exhausted_until: float = 0.0
    last_call_at: float    = 0.0   # per-key RPM tracking
    error_count: int       = 0

    @property
    def is_available(self) -> bool:
        return time.monotonic() >= self.exhausted_until

    @property
    def seconds_until_ready(self) -> float:
        """Bao nhiêu giây nữa key này có thể dùng được (tính cả RPM interval)."""
        cooldown_wait = max(0.0, self.exhausted_until - time.monotonic())
        rpm_wait      = max(0.0, self.last_call_at + PER_KEY_MIN_INTERVAL - time.monotonic())
        return max(cooldown_wait, rpm_wait)

    @property
    def is_ready_now(self) -> bool:
        return self.seconds_until_ready == 0.0

    def mark_exhausted(self, cooldown: float = COOLDOWN_SECONDS) -> None:
        self.exhausted_until = time.monotonic() + cooldown
        self.error_count    += 1
        logger.warning(
            f"[GeminiRotator] Key #{self.index} rate-limited → cooldown {cooldown:.0f}s"
        )

    def mark_called(self) -> None:
        self.last_call_at = time.monotonic()
        self.error_count  = 0


# ── Response Wrapper (Groq-compatible interface) ──────────────────────────────

class _Message:
    def __init__(self, content: str):
        self.content = content

class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)

class _GeminiResponse:
    def __init__(self, text: str):
        self.choices = [_Choice(text)]


# ── Rotator Core ──────────────────────────────────────────────────────────────

class GeminiRotatorClient:
    """
    Drop-in replacement cho GroqRotatorClient.

    Usage:
        judge = GeminiRotatorClient()
        resp  = judge.chat.completions.create(
            model           = "gemma-3-31b-it",
            messages        = [{"role": "user", "content": prompt}],
            response_format = {"type": "json_object"},
        )
        text = resp.choices[0].message.content
    """

    def __init__(
        self,
        api_keys: list[str] | None = None,
        api_key:  str | None       = None,
    ):
        if api_key and not api_keys:
            api_keys = [k.strip() for k in api_key.split(",") if k.strip()]

        keys = api_keys or self._load_keys_from_env()
        if not keys:
            raise ValueError(
                "No Google API keys found. "
                "Set GOOGLE_API_KEY=key1,key2 or GOOGLE_API_KEY_1, _2, ..."
            )

        self._slots: list[_KeySlot] = [
            _KeySlot(api_key=k, index=i) for i, k in enumerate(keys)
        ]
        self._lock = Lock()
        self.chat  = _ChatNamespace(self)

        logger.info(
            f"[GeminiRotator] {len(self._slots)} key(s) | "
            f"interval={PER_KEY_MIN_INTERVAL}s/key | cooldown={COOLDOWN_SECONDS}s"
        )

    @staticmethod
    def _load_keys_from_env() -> list[str]:
        multi = os.getenv("GOOGLE_API_KEY", "")
        keys  = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys
        numbered = []
        for i in range(1, 20):
            k = os.getenv(f"GOOGLE_API_KEY_{i}", "").strip()
            if k:
                numbered.append(k)
        return numbered

    # ── Smart slot selection ──────────────────────────────────────────────────

    def _get_best_slot(self) -> _KeySlot:
        """
        Luôn trả về slot tốt nhất:
          - Ưu tiên slot is_ready_now, chọn cái lâu nhất chưa được gọi (fairness)
          - Nếu không có slot nào ready → chọn cái sẽ ready sớm nhất
        Không bao giờ raise exception — caller tự xử lý việc chờ.
        """
        ready = [s for s in self._slots if s.is_ready_now]
        if ready:
            return min(ready, key=lambda s: s.last_call_at)
        return min(self._slots, key=lambda s: s.seconds_until_ready)

    # ── Core call ─────────────────────────────────────────────────────────────

    def call_with_rotation(
        self,
        model: str,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.0,
        **kwargs,
    ) -> _GeminiResponse:
        """
        Gọi Gemini với per-key RPM tracking và smart wait.

        Flow:
          1. Chọn slot tốt nhất
          2. Nếu slot cần chờ → sleep đúng thời gian
          3. Gọi API
          4. Nếu rate limit → mark slot exhausted, chọn slot khác
          5. Không bao giờ throw RuntimeError vì hết attempts —
             chỉ throw khi lỗi không phải rate limit (auth, model not found...)
        """
        # Tối đa slots*3 lần thử (mỗi key thử tối đa 3 lần sau cooldown)
        max_retries = len(self._slots) * 3

        for attempt in range(max_retries):
            with self._lock:
                slot = self._get_best_slot()

            wait = slot.seconds_until_ready
            if wait > 0:
                logger.info(
                    f"[GeminiRotator] Key #{slot.index} ready in {wait:.1f}s → waiting..."
                )
                time.sleep(wait + 0.5)

            genai.configure(api_key=slot.api_key)

            try:
                gen_config: dict = {"temperature": temperature}
                # Gemma 4 via google.generativeai không hỗ trợ response_mime_type
                # JSON extraction được xử lý bằng prompt + _extract_json()

                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]

                prompt = self._build_prompt(messages)

                model_obj = genai.GenerativeModel(
                    model_name        = model,
                    generation_config = gen_config,
                    safety_settings   = safety_settings,
                )
                response = model_obj.generate_content(prompt)
                raw_text = response.text or ""
                text     = _extract_json(raw_text)

                if not text:
                    logger.warning(f"[GeminiRotator] Key #{slot.index} returned empty/invalid JSON. Raw: {raw_text[:200]!r}")
                    # Coi như lỗi parse để retry slot khác
                    raise json.JSONDecodeError("empty response", raw_text, 0)

                slot.mark_called()
                logger.debug(f"[GeminiRotator] Key #{slot.index} OK | {len(text)} chars")
                return _GeminiResponse(text)

            except ResourceExhausted:
                logger.warning(
                    f"[GeminiRotator] Key #{slot.index} ResourceExhausted "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                slot.mark_exhausted()

            except (ServiceUnavailable, InternalServerError) as e:
                logger.warning(f"[GeminiRotator] Key #{slot.index} ServerError ({type(e).__name__}): {str(e)[:80]}")
                slot.mark_exhausted(cooldown=20)

            except GoogleAPIError as e:
                err = str(e).lower()
                if any(kw in err for kw in ("quota", "rate", "429", "resource_exhausted")):
                    slot.mark_exhausted()
                elif "500" in err or "internal error" in err:
                    logger.warning(f"[GeminiRotator] Key #{slot.index} 500 via GoogleAPIError: {str(e)[:80]}")
                    slot.mark_exhausted(cooldown=20)
                else:
                    raise  # auth error, model not found → jangan retry

            except Exception as e:
                err = str(e).lower()
                if "500" in err or "internal error" in err:
                    logger.warning(f"[GeminiRotator] Key #{slot.index} 500 via Exception: {str(e)[:80]}")
                    slot.mark_exhausted(cooldown=20)
                else:
                    raise

        # Nếu vẫn fail sau max_retries, chờ slot sớm nhất và thử 1 lần cuối
        with self._lock:
            last_slot = self._get_best_slot()
        final_wait = last_slot.seconds_until_ready
        if final_wait > 0:
            logger.warning(f"[GeminiRotator] Final wait {final_wait:.1f}s for key #{last_slot.index}")
            time.sleep(final_wait + 1.0)

        # Final attempt với try-except để không crash evaluator
        try:
            genai.configure(api_key=last_slot.api_key)
            gen_config = {"temperature": temperature}
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            model_obj = genai.GenerativeModel(
                model, generation_config=gen_config, safety_settings=safety_settings
            )
            response  = model_obj.generate_content(self._build_prompt(messages))
            raw_text  = response.text or ""
            text      = _extract_json(raw_text)
            last_slot.mark_called()
            return _GeminiResponse(text)
        except Exception as e:
            logger.error(f"[GeminiRotator] Final attempt failed: {str(e)[:120]}")
            # Trả về JSON default để evaluator không crash
            return _GeminiResponse('{"reasoning": "JUDGE_500_ERROR", "context_recall": 0.0, "context_precision": 0.0, "strict_faithfulness": 0.0, "answer_completeness": 0.0, "issue": "OK"}')

    @staticmethod
    def _build_prompt(messages: list[dict]) -> str:
        """Convert OpenAI messages → single string cho Gemini."""
        system_parts, user_parts = [], []
        for msg in messages:
            role    = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                user_parts.append(content)

        parts = []
        if system_parts:
            parts.append("\n\n".join(system_parts))
        if user_parts:
            parts.append("\n\n".join(user_parts))
        return "\n\n".join(parts)


# ── Groq-compatible namespace wrappers ────────────────────────────────────────

class _CompletionsNamespace:
    def __init__(self, rotator: GeminiRotatorClient):
        self._r = rotator

    def create(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        response_format: dict | None = None,
        **kwargs,
    ) -> _GeminiResponse:
        return self._r.call_with_rotation(
            model           = model,
            messages        = messages,
            response_format = response_format,
            temperature     = temperature,
        )


class _ChatNamespace:
    def __init__(self, rotator: GeminiRotatorClient):
        self.completions = _CompletionsNamespace(rotator)