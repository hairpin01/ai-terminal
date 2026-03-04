from __future__ import annotations

import json
from pathlib import Path


class HistoryStore:
    def __init__(self, history_file: Path):
        self.history_file = history_file
        self._items: list[dict[str, str]] = []

    @property
    def items(self) -> list[dict[str, str]]:
        return list(self._items)

    def load(self) -> None:
        try:
            if self.history_file.exists():
                with self.history_file.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, list):
                    self._items = [item for item in data if isinstance(item, dict)]
                else:
                    self._items = []
            else:
                self._items = []
                self.save()
        except Exception:
            self._items = []

    def save(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with self.history_file.open("w", encoding="utf-8") as fp:
                json.dump(self._items, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, role: str, content: str, memory_depth: int) -> None:
        if not content:
            return

        self._items.append({"role": role, "content": content})
        max_history = max(1, memory_depth) * 2
        if len(self._items) > max_history:
            self._items = self._items[-max_history:]

        self.save()

    def clear(self) -> None:
        self._items = []
        self.save()
