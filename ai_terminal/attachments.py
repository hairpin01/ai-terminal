from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Attachment:
    path: str
    name: str
    content: str
    size: int
    attached_at: str


class AttachmentManager:
    def __init__(self):
        self._files: list[Attachment] = []

    def attach_file(self, file_path: str) -> tuple[bool, str]:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return False, f"❌ File not found: {file_path}"
        if not path.is_file():
            return False, f"❌ Not a file: {file_path}"

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False, f"❌ File is not UTF-8 text: {file_path}"
        except Exception as exc:
            return False, f"❌ Failed to read file: {exc}"

        attachment = Attachment(
            path=str(path),
            name=path.name,
            content=content,
            size=len(content),
            attached_at=datetime.now().isoformat(),
        )
        self._files.append(attachment)
        return True, f"📎 Attached: {path.name} ({len(content)} chars)"

    def clear(self) -> None:
        self._files.clear()

    def summaries(self) -> list[str]:
        return [f"{idx}. {f.name} ({f.size} chars)" for idx, f in enumerate(self._files, 1)]

    def build_prompt(self, question: str) -> str:
        if not self._files:
            return question

        blocks = []
        for file_info in self._files:
            blocks.append(
                f"\n\n--- File: {file_info.name} ---\n"
                f"{file_info.content}\n"
                "--- End of file ---"
            )

        return f"{question}\n\nAttached files:{''.join(blocks)}"

    def count(self) -> int:
        return len(self._files)
