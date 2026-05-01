from __future__ import annotations

import os
import time
import logging
from threading import Lock
from dataclasses import dataclass, field

from groq import Groq, RateLimitError, APIStatusError

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 60



@dataclass
class _KeySlot:
    api_key: str
    index: int
    exhausted_until: float = 0.0
    error_count: int = 0

    @property
    def is_available(self) -> bool:
        return time.monotonic() >= self.exhausted_until

    def mark_exhausted(self, cooldown: float = COOLDOWN_SECONDS) -> None:
        self.exhausted_until = time.monotonic() + cooldown
        self.error_count += 1
        logger.warning(
            f"[Rotator] Key #{self.index} rate-limited → cooldown {cooldown:.0f}s"
        )

    def mark_ok(self) -> None:
        self.error_count = 0


class GroqRotatorClient:
    def __init__(self, api_keys: list[str] | None = None, api_key: str | None = None):
        if api_key and not api_keys:
            api_keys = [k.strip() for k in api_key.split(",") if k.strip()]

        keys = api_keys or self._load_keys_from_env()

        if not keys:
            raise ValueError("No GROQ API keys found")

        self._slots = [_KeySlot(api_key=k, index=i) for i, k in enumerate(keys)]
        self._current_idx = 0
        self._lock = Lock()

        self._clients = {
            slot.index: Groq(api_key=slot.api_key)
            for slot in self._slots
        }

        self.chat = _ChatNamespace(self)

    @staticmethod
    def _load_keys_from_env() -> list[str]:
        multi = os.getenv("GROQ_API_KEY", "")
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys

        numbered = []
        for i in range(1, 20):
            k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
            if k:
                numbered.append(k)
        return numbered

    def _get_available_slot(self) -> _KeySlot | None:
        n = len(self._slots)
        for offset in range(n):
            slot = self._slots[(self._current_idx + offset) % n]
            if slot.is_available:
                return slot
        return None

    def _rotate(self) -> None:
        self._current_idx = (self._current_idx + 1) % len(self._slots)

    def call_with_rotation(self, method_path: str, **kwargs):
        max_attempts = len(self._slots) * 2

        for attempt in range(max_attempts):
            with self._lock:
                slot = self._get_available_slot()

            if slot is None:
                soonest = min(self._slots, key=lambda s: s.exhausted_until)
                wait = max(0.0, soonest.exhausted_until - time.monotonic())
                time.sleep(wait + 0.5)
                slot = soonest

            client = self._clients[slot.index]

            try:
                obj = client
                for part in method_path.split("."):
                    obj = getattr(obj, part)

                result = obj(**kwargs)
                slot.mark_ok()
                return result

            except RateLimitError:
                slot.mark_exhausted()
                with self._lock:
                    self._rotate()

            except APIStatusError as e:
                if e.status_code in (429, 503):
                    slot.mark_exhausted()
                    with self._lock:
                        self._rotate()
                else:
                    raise

        raise RuntimeError("All Groq API keys failed")


class _CompletionsNamespace:
    def __init__(self, rotator: GroqRotatorClient):
        self._r = rotator

    def create(self, **kwargs):
        return self._r.call_with_rotation("chat.completions.create", **kwargs)


class _ChatNamespace:
    def __init__(self, rotator: GroqRotatorClient):
        self.completions = _CompletionsNamespace(rotator)