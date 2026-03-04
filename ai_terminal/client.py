from __future__ import annotations

import configparser
import json
import re
from typing import Callable

import openai

from .file_tools import FileToolExecutor


class OpenAIChatClient:
    def __init__(self, config: configparser.ConfigParser):
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.get("api", "api_key"),
            base_url=config.get("api", "base_url"),
        )

    def ask(self, messages: list[dict[str, str]]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.config.get("api", "model_name"),
                messages=messages,
                temperature=self.config.getfloat("settings", "temperature", fallback=0.7),
                max_tokens=self.config.getint("settings", "max_tokens", fallback=4096),
            )
            if response and response.choices:
                answer = self._message_content_to_text(response.choices[0].message.content)
                if answer:
                    return answer.strip()
                return "⚠️ Empty response received from AI"
            return "⚠️ No response received from AI"
        except openai.APIError as exc:
            return f"❌ API error: {exc}"
        except openai.OpenAIError as exc:
            return f"❌ OpenAI error: {exc}"
        except Exception as exc:
            return f"❌ Unexpected error: {exc}"

    def ask_with_file_tools(
        self,
        messages: list[dict[str, str]],
        tool_executor: FileToolExecutor,
        max_steps: int,
        event_callback: Callable[[dict[str, str]], None] | None = None,
    ) -> tuple[str, list[str], str]:
        tool_log: list[str] = []
        auto_diff_text = ""
        working_messages: list[dict] = [dict(item) for item in messages]
        step_limit = max(1, max_steps)
        stream_final = (
            event_callback is not None
            and self.config.getboolean("settings", "agent_stream_final", fallback=True)
        )
        forced_retry_used = False
        force_tool_next = False

        for _ in range(step_limit):
            self._emit(event_callback, "status", "🔎 Planning next step...")
            try:
                response = self.client.chat.completions.create(
                    model=self.config.get("api", "model_name"),
                    messages=working_messages,
                    tools=tool_executor.openai_tools(),
                    tool_choice="required" if force_tool_next else "auto",
                    temperature=self.config.getfloat("settings", "temperature", fallback=0.7),
                    max_tokens=self.config.getint("settings", "max_tokens", fallback=4096),
                )
                force_tool_next = False
            except openai.APIError as exc:
                if self._looks_like_tool_unsupported(str(exc)):
                    fallback = self.ask(messages)
                    tool_log.append("Tool-calling unsupported by backend; used plain completion")
                    self._emit(event_callback, "status", "Tool-calling unsupported, fallback to plain mode")
                    return fallback, tool_log, auto_diff_text
                return f"❌ API error: {exc}", tool_log, auto_diff_text
            except openai.OpenAIError as exc:
                return f"❌ OpenAI error: {exc}", tool_log, auto_diff_text
            except Exception as exc:
                return f"❌ Unexpected error: {exc}", tool_log, auto_diff_text

            if not response or not response.choices:
                return "⚠️ No response received from AI", tool_log, auto_diff_text

            message = response.choices[0].message
            assistant_text = self._message_content_to_text(message.content)
            tool_calls = list(getattr(message, "tool_calls", None) or [])

            if not tool_calls:
                textual_tool = self._extract_textual_tool_call(assistant_text or "")
                if textual_tool is not None:
                    tool_name, arguments = textual_tool
                    status_text, display_action = self._format_tool_activity(tool_name, arguments)
                    tool_result = tool_executor.execute(tool_name, arguments)
                    tool_log.append(display_action)
                    self._emit(event_callback, "status", status_text)
                    self._emit(event_callback, "tool", display_action)
                    working_messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_text,
                        }
                    )
                    working_messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"Tool result for {display_action}:\n{tool_result}\n\n"
                                "Continue the analysis. If more data is needed, call another tool. "
                                "When done, provide the final answer without raw tool-call syntax."
                            ),
                        }
                    )
                    continue

                if (
                    assistant_text
                    and self._looks_like_no_access_refusal(assistant_text)
                    and not forced_retry_used
                ):
                    forced_retry_used = True
                    force_tool_next = True
                    self._emit(event_callback, "status", "⚠️ Model skipped tools, forcing tool usage...")
                    working_messages.append(
                        {
                            "role": "system",
                            "content": (
                                "You DO have access to local file tools in this chat. "
                                "Do not say you cannot access files or run checks. "
                                "Call at least one tool now."
                            ),
                        }
                    )
                    continue

                if assistant_text:
                    if stream_final:
                        streamed_answer = self._stream_final_answer(
                            messages=working_messages,
                            event_callback=event_callback,
                        )
                        if streamed_answer:
                            answer_text = streamed_answer.strip()
                            auto_diff_text = self._emit_auto_diff_if_changed(
                                tool_executor=tool_executor,
                                event_callback=event_callback,
                                tool_log=tool_log,
                            )
                            return answer_text, tool_log, auto_diff_text
                    self._emit(event_callback, "status", "✍️ Writing final answer...")
                    self._emit(event_callback, "final_start", "")
                    for chunk in self.chunk_text(assistant_text.strip()):
                        self._emit(event_callback, "final_chunk", chunk)
                    self._emit(event_callback, "final_end", "")
                    answer_text = assistant_text.strip()
                    auto_diff_text = self._emit_auto_diff_if_changed(
                        tool_executor=tool_executor,
                        event_callback=event_callback,
                        tool_log=tool_log,
                    )
                    return answer_text, tool_log, auto_diff_text
                return "⚠️ Empty response received from AI", tool_log, auto_diff_text

            assistant_payload: dict = {
                "role": "assistant",
                "content": assistant_text or "",
                "tool_calls": [],
            }

            for index, tool_call in enumerate(tool_calls, 1):
                fn = getattr(tool_call, "function", None)
                tool_name = getattr(fn, "name", "") if fn else ""
                arguments = getattr(fn, "arguments", "{}") if fn else "{}"
                call_id = getattr(tool_call, "id", "") or f"call_{index}"

                assistant_payload["tool_calls"].append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": arguments,
                        },
                    }
                )

            working_messages.append(assistant_payload)

            for index, tool_call in enumerate(tool_calls, 1):
                fn = getattr(tool_call, "function", None)
                tool_name = getattr(fn, "name", "") if fn else ""
                arguments = getattr(fn, "arguments", "{}") if fn else "{}"
                call_id = getattr(tool_call, "id", "") or f"call_{index}"

                tool_result = tool_executor.execute(tool_name, arguments)
                status_text, display_action = self._format_tool_activity(tool_name, arguments)
                tool_log.append(display_action)
                self._emit(event_callback, "status", status_text)
                self._emit(event_callback, "tool", display_action)

                working_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": tool_result,
                    }
                )

        auto_diff_text = self._emit_auto_diff_if_changed(
            tool_executor=tool_executor,
            event_callback=event_callback,
            tool_log=tool_log,
        )
        return "⚠️ Agent step limit reached before final answer", tool_log, auto_diff_text

    def _stream_final_answer(
        self,
        messages: list[dict],
        event_callback: Callable[[dict[str, str]], None] | None,
    ) -> str:
        self._emit(event_callback, "status", "✍️ Writing final answer...")

        parts: list[str] = []
        started = False
        try:
            stream = self.client.chat.completions.create(
                model=self.config.get("api", "model_name"),
                messages=messages,
                temperature=self.config.getfloat("settings", "temperature", fallback=0.7),
                max_tokens=self.config.getint("settings", "max_tokens", fallback=4096),
                stream=True,
            )
            for chunk in stream:
                if not chunk or not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                piece = self._delta_content_to_text(getattr(delta, "content", None))
                if not piece:
                    continue
                if not started:
                    self._emit(event_callback, "final_start", "")
                    started = True
                parts.append(piece)
                self._emit(event_callback, "final_chunk", piece)
        except Exception:
            if started:
                self._emit(event_callback, "final_end", "")
            return ""

        if started:
            self._emit(event_callback, "final_end", "")
        return "".join(parts)

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 32) -> list[str]:
        if chunk_size <= 0:
            chunk_size = 32
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    @staticmethod
    def _looks_like_tool_unsupported(error_text: str) -> bool:
        lowered = error_text.lower()
        return (
            "tool" in lowered
            or "function call" in lowered
            or "function_call" in lowered
            or "unsupported parameter" in lowered
        )

    @staticmethod
    def _looks_like_no_access_refusal(text: str) -> bool:
        lowered = text.lower()
        markers = [
            "can't execute",
            "cannot execute",
            "cannot run",
            "can't run",
            "no access",
            "don't have access",
            "unable to",
            "requires access",
            "cannot automatically",
            "не могу",
            "нет доступа",
            "не смог",
            "требуется доступ",
        ]
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _compact_arguments(arguments: str, limit: int = 80) -> str:
        text = arguments.replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    @staticmethod
    def _extract_textual_tool_call(text: str) -> tuple[str, str] | None:
        if not text:
            return None

        tool_names = (
            "list_files|read_file|search_files|grep_files|write_file|replace_in_file|diff_changes"
        )
        patterns = [
            rf"({tool_names})\s*\(\s*(\{{[\s\S]*?\}})\s*\)",
            rf"({tool_names})\s*(\{{[\s\S]*?\}})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            tool_name = (match.group(1) or "").strip().lower()
            arguments = (match.group(2) or "").strip()
            if tool_name and arguments:
                return tool_name, arguments

        grep_phrase = re.search(
            r"grep\s+['\"]([^'\"]+)['\"]\s+in\s+([^\s]+)",
            text,
            flags=re.IGNORECASE,
        )
        if grep_phrase:
            query = (grep_phrase.group(1) or "").strip()
            path = (grep_phrase.group(2) or "").strip()
            if query:
                return "grep_files", json.dumps({"query": query, "path": path})

        no_arg = re.search(rf"\b({tool_names})\s*\(\s*\)", text, flags=re.IGNORECASE)
        if no_arg:
            return (no_arg.group(1) or "").strip().lower(), "{}"

        return None

    @staticmethod
    def _message_content_to_text(content: object) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text = item.get("text", "")
                        if isinstance(text, str):
                            parts.append(text)
                    elif isinstance(item.get("text"), str):
                        parts.append(item["text"])
                elif hasattr(item, "text") and isinstance(item.text, str):
                    parts.append(item.text)
            return "\n".join(part for part in parts if part)
        return str(content)

    @staticmethod
    def _delta_content_to_text(content: object) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif hasattr(item, "text") and isinstance(item.text, str):
                    parts.append(item.text)
            return "".join(parts)
        return str(content)

    @staticmethod
    def _emit(
        callback: Callable[[dict[str, str]], None] | None,
        event_type: str,
        text: str,
    ) -> None:
        if callback is None:
            return
        callback({"type": event_type, "text": text})

    def _emit_auto_diff_if_changed(
        self,
        tool_executor: FileToolExecutor,
        event_callback: Callable[[dict[str, str]], None] | None,
        tool_log: list[str],
    ) -> str:
        if not tool_executor.has_changes():
            return ""

        diff_text = tool_executor.get_changes_diff()
        if not diff_text or diff_text.startswith("No "):
            return ""

        self._emit(event_callback, "status", "📄 Building diff...")
        self._emit(event_callback, "tool", "Show diff of changed files")
        self._emit(event_callback, "diff", diff_text)
        tool_log.append("Show diff of changed files")
        return diff_text

    @staticmethod
    def _format_tool_activity(tool_name: str, arguments: str) -> tuple[str, str]:
        payload = OpenAIChatClient._load_json_dict(arguments)
        name = (tool_name or "").strip()

        def val(key: str, default: object) -> object:
            value = payload.get(key, default)
            if value == "" or value is None:
                return default
            return value

        if name == "list_files":
            path = val("path", ".")
            recursive = val("recursive", True)
            max_entries = val("max_entries", "default")
            text = f"Read in {path} [recursive={recursive}] [max_entries={max_entries}]"
            return text, text

        if name == "read_file":
            path = val("path", "")
            start_line = val("start_line", 1)
            max_lines = val("max_lines", "default")
            text = f"Read file {path} [start_line={start_line}] [max_lines={max_lines}]"
            return text, text

        if name == "search_files":
            pattern = val("pattern", "")
            path = val("path", ".")
            file_glob = val("file_glob", "*")
            max_results = val("max_results", "default")
            text = (
                f"Search /{pattern}/ in {path} [file_glob={file_glob}] "
                f"[max_results={max_results}]"
            )
            return text, text

        if name == "grep_files":
            query = val("query", "")
            path = val("path", ".")
            file_glob = val("file_glob", "*")
            max_results = val("max_results", "default")
            text = (
                f"Grep '{query}' in {path} [file_glob={file_glob}] "
                f"[max_results={max_results}]"
            )
            return text, text

        if name == "write_file":
            path = val("path", "")
            content = val("content", "")
            text = f"Write file {path} [chars={len(str(content))}]"
            return text, text

        if name == "replace_in_file":
            path = val("path", "")
            replace_all = val("replace_all", False)
            search = val("search", "")
            replace = val("replace", "")
            text = (
                f"Edit file {path} [replace_all={replace_all}] "
                f"[search_chars={len(str(search))}] [replace_chars={len(str(replace))}]"
            )
            return text, text

        if name == "diff_changes":
            text = "Show diff of changed files"
            return text, text

        fallback = f"{name}({OpenAIChatClient._compact_arguments(arguments)})"
        return f"Run {name}", fallback

    @staticmethod
    def _load_json_dict(arguments: str) -> dict:
        try:
            parsed = json.loads(arguments) if arguments else {}
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}
