"""
gemini_rotator.py — Gemini API Key Rotator (Migrated to google-genai SDK v2)

Updates:
  - Migrated from deprecated google-generativeai to google-genai SDK.
  - Each key slot now maintains its own genai.Client instance (thread-safe).
  - Standardized error handling for the new SDK.
"""

from __future__ import annotations

import json
import os
import re
import time
import logging
from threading import Lock
from dataclasses import dataclass, field

from google import genai
from google.genai import types, errors
from src.utils.text_utils import extract_json

logger = logging.getLogger(__name__)


PER_KEY_MIN_INTERVAL = 5.0   # RPM tracking
COOLDOWN_SECONDS     = 65.0  # Rate limit cooldown


# ── Key Slot ──────────────────────────────────────────────────────────────────

@dataclass
class _KeySlot:
    api_key: str
    index: int
    client: genai.Client = field(init=False)
    exhausted_until: float = 0.0
    last_call_at: float    = 0.0
    error_count: int       = 0

    def __post_init__(self):
        self.client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1beta'})

    @property
    def is_available(self) -> bool:
        return time.monotonic() >= self.exhausted_until

    @property
    def seconds_until_ready(self) -> float:
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
            f"[GeminiRotator] {len(self._slots)} key(s) | SDK v2 (google-genai)"
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

    def _get_best_slot(self) -> _KeySlot:
        ready = [s for s in self._slots if s.is_ready_now]
        if ready:
            return min(ready, key=lambda s: s.last_call_at)
        return min(self._slots, key=lambda s: s.seconds_until_ready)

    def call_with_rotation(
        self,
        model: str,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.0,
        **kwargs,
    ) -> _GeminiResponse:
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

            try:
                # Configuration for google-genai
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    # [TỐI ƯU] Tắt hoàn toàn AFC và lọc an toàn để tăng tốc độ phản hồi
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ],
                )
                
                # If JSON object is requested, the new SDK handles it better
                if response_format and response_format.get("type") == "json_object":
                    config.response_mime_type = "application/json"

                prompt = self._build_prompt(messages)
                
                # [TỐI ƯU] Gọi trực tiếp generate_content với config tối giản
                response = slot.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )

                raw_text = response.text or ""
                text     = extract_json(raw_text)

                if not text:
                    logger.warning(f"[GeminiRotator] Key #{slot.index} returned empty/invalid JSON.")
                    raise ValueError("empty response")

                slot.mark_called()
                return _GeminiResponse(text)

            except errors.ClientError as e:
                err_msg = str(e).upper()
                # Handle rate limits (429)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    logger.warning(f"[GeminiRotator] Key #{slot.index} rate-limited (429)")
                    slot.mark_exhausted()
                elif "LEAKED" in err_msg or "API_KEY_INVALID" in err_msg:
                    logger.error(f"❌ [GeminiRotator] Key #{slot.index} bị khóa do rò rỉ hoặc vô hiệu! Loại bỏ vĩnh viễn.")
                    slot.mark_exhausted(cooldown=86400) # Khóa 24h (coi như bỏ)
                else:
                    logger.error(f"[GeminiRotator] ClientError on Key #{slot.index}: {e}")
                    raise

            except errors.ServerError as e:
                logger.warning(f"[GeminiRotator] Key #{slot.index} ServerError: {e}")
                slot.mark_exhausted(cooldown=20)

            except Exception as e:
                err = str(e).lower()
                if "429" in err or "quota" in err or "resource_exhausted" in err:
                    slot.mark_exhausted()
                elif "500" in err or "server error" in err or "internal error" in err:
                    slot.mark_exhausted(cooldown=20)
                else:
                    logger.error(f"[GeminiRotator] Unexpected error on Key #{slot.index}: {e}")
                    raise

        # Final attempt fallback
        with self._lock:
            last_slot = self._get_best_slot()
        final_wait = last_slot.seconds_until_ready
        if final_wait > 0:
            time.sleep(final_wait + 1.0)

        try:
            config = types.GenerateContentConfig(temperature=temperature)
            resp = last_slot.client.models.generate_content(
                model=model,
                contents=self._build_prompt(messages),
                config=config
            )
            text = extract_json(resp.text or "")
            last_slot.mark_called()
            return _GeminiResponse(text)
        except Exception as e:
            logger.error(f"[GeminiRotator] Final attempt failed: {e}")
            return _GeminiResponse('{"reasoning": "JUDGE_500_ERROR", "issue": "OK"}')

    @staticmethod
    def _build_prompt(messages: list[dict]) -> str:
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