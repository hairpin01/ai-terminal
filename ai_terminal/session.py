from __future__ import annotations

import configparser
from pathlib import Path
from typing import Callable

from .attachments import AttachmentManager
from .client import OpenAIChatClient
from .file_tools import FileToolExecutor
from .history import HistoryStore


class ChatSession:
    def __init__(self, config: configparser.ConfigParser, history_file: Path):
        self.config = config
        self.history = HistoryStore(history_file)
        self.history.load()

        self.attachments = AttachmentManager()
        self.client = OpenAIChatClient(config)
        self.last_agent_actions: list[str] = []
        self.last_agent_diff: str = ""

    def history_messages(self) -> list[dict[str, str]]:
        return self.history.items

    def clear_history(self) -> None:
        self.history.clear()

    def attach_file(self, file_path: str) -> tuple[bool, str]:
        return self.attachments.attach_file(file_path)

    def clear_attached_files(self) -> str:
        self.attachments.clear()
        return "🧹 Attached files cleared"

    def attached_files_text(self) -> str:
        summaries = self.attachments.summaries()
        if not summaries:
            return "📎 No attached files"
        return "📎 Attached files:\n" + "\n".join(summaries)

    def is_agent_file_tools_enabled(self) -> bool:
        return self.config.getboolean("settings", "agent_file_tools", fallback=True)

    def set_agent_file_tools_enabled(self, enabled: bool) -> str:
        if not self.config.has_section("settings"):
            self.config.add_section("settings")
        self.config.set("settings", "agent_file_tools", "true" if enabled else "false")
        state = "enabled" if enabled else "disabled"
        return f"🛠️ Agent file mode {state}"

    def get_agent_mode(self) -> str:
        mode = self.config.get("settings", "agent_mode", fallback="plan").strip().lower()
        return "build" if mode == "build" else "plan"

    def set_agent_mode(self, mode: str) -> str:
        normalized = "build" if (mode or "").strip().lower() == "build" else "plan"
        if not self.config.has_section("settings"):
            self.config.add_section("settings")
        self.config.set("settings", "agent_mode", normalized)
        return f"🧭 Agent mode set to {normalized.upper()}"

    def ask(
        self,
        question: str,
        on_event: Callable[[dict[str, str]], None] | None = None,
    ) -> tuple[bool, str]:
        full_prompt = self.attachments.build_prompt(question)
        self.last_agent_actions = []
        self.last_agent_diff = ""

        use_agent_file_tools = self.is_agent_file_tools_enabled()
        agent_mode = self.get_agent_mode()
        if on_event and use_agent_file_tools:
            on_event({"type": "status", "text": f"🧭 Mode: {agent_mode.upper()}"})

        system_prompt = self.config.get("settings", "system_prompt")
        if use_agent_file_tools:
            system_prompt = (
                f"{system_prompt}\n\n"
                "You can use tools to inspect local project files. "
                "When the user asks about code/files/bugs, call tools first, then answer. "
                "Never output raw tool-call text like read_file{...} in the final answer.\n"
                f"Current mode: {agent_mode.upper()}.\n"
                "PLAN mode: do not edit files, provide analysis and concrete plan only.\n"
                "BUILD mode: you may edit files and should call diff_changes before final response "
                "if any file was modified.\n"
                "Use grep_files when user asks to grep patterns, e.g. Grep 'text*.txt' in test/."
            )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(self.history.items)
        messages.append({"role": "user", "content": full_prompt})

        if use_agent_file_tools:
            executor = FileToolExecutor(
                workspace_root=Path.cwd(),
                mode=agent_mode,
                max_list_entries=self.config.getint(
                    "settings", "agent_list_max_entries", fallback=1500
                ),
                max_read_lines=self.config.getint(
                    "settings", "agent_read_max_lines", fallback=1200
                ),
                max_read_chars=self.config.getint(
                    "settings", "agent_read_max_chars", fallback=200000
                ),
                max_search_results=self.config.getint(
                    "settings", "agent_search_max_results", fallback=1000
                ),
                max_file_bytes=self.config.getint(
                    "settings", "agent_max_file_bytes", fallback=1000000
                ),
                max_scan_files=self.config.getint(
                    "settings", "agent_max_scan_files", fallback=10000
                ),
                max_write_chars=self.config.getint(
                    "settings", "agent_max_write_chars", fallback=400000
                ),
                max_diff_chars=self.config.getint(
                    "settings", "agent_max_diff_chars", fallback=300000
                ),
            )
            answer, actions, diff_text = self.client.ask_with_file_tools(
                messages=messages,
                tool_executor=executor,
                max_steps=self.config.getint("settings", "agent_max_steps", fallback=16),
                event_callback=on_event,
            )
            self.last_agent_actions = actions
            self.last_agent_diff = diff_text
        else:
            answer = self.client.ask(messages)
            if on_event and answer and not (answer.startswith("❌") or answer.startswith("⚠️")):
                on_event({"type": "final_start", "text": ""})
                for chunk in self.client.chunk_text(answer):
                    on_event({"type": "final_chunk", "text": chunk})
                on_event({"type": "final_end", "text": ""})

        if not answer:
            return False, "⚠️ Empty AI response"
        if answer.startswith("❌") or answer.startswith("⚠️"):
            return False, answer

        memory_depth = self.config.getint("settings", "memory_depth", fallback=5)
        self.history.add("user", question, memory_depth)
        self.history.add("assistant", answer, memory_depth)

        self.attachments.clear()
        return True, answer
