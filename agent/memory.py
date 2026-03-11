"""Session memory utilities for multi-turn chat context."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionMemory:
    """Stores recent conversation turns with a sliding window."""

    max_messages: int = 20
    _history: list[dict] = field(default_factory=list)

    def add_turn(self, role: str, content: str) -> None:
        if role not in {"user", "assistant", "system"}:
            return
        text = str(content or "").strip()
        if not text:
            return
        self._history.append({"role": role, "content": text})
        if len(self._history) > self.max_messages:
            self._history = self._history[-self.max_messages :]

    def get_history(self) -> list[dict]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
