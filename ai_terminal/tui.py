from __future__ import annotations

import curses
import queue
import threading
import time

from .formatting import StyledSpan, markdown_to_styled_lines, wrap_styled_line
from .session import ChatSession
from .shell import run_shell_command


class TerminalUI:
    ROLE_PREFIXES = {
        "user": "You: ",
        "assistant": "AI: ",
        "system": "System: ",
        "tool": "",
        "error": "Error: ",
    }

    COMMANDS = [
        ("/help", "show help"),
        ("/clear", "clear chat history"),
        ("/file <path>", "attach a file"),
        ("/files", "list attached files"),
        ("/clear_files", "clear attached files"),
        ("/agent", "show agent file mode status"),
        ("/agent on|off", "toggle agent file mode"),
        ("/mode", "show current mode"),
        ("/mode plan|build", "set plan/build mode"),
        ("/quit", "exit TUI"),
    ]

    def __init__(self, session: ChatSession):
        self.session = session
        self.messages: list[tuple[str, str]] = []
        self.input_buffer = ""
        self.running = True
        self.status_text = "Ready"
        self.scroll_offset = 0
        self.last_chat_height = 1

        for message in self.session.history_messages():
            role = message.get("role", "assistant")
            content = message.get("content", "")
            self.messages.append((role, content))

        self.attrs: dict[str, int] = {
            "header": curses.A_BOLD,
            "status": curses.A_DIM,
            "input": curses.A_NORMAL,
            "normal": curses.A_NORMAL,
            "bold": curses.A_BOLD,
            "italic": curses.A_DIM,
            "code": curses.A_NORMAL,
            "heading": curses.A_BOLD,
            "muted": curses.A_DIM,
            "error": curses.A_BOLD,
            "user": curses.A_BOLD,
            "assistant": curses.A_BOLD,
            "system": curses.A_BOLD,
            "tool": curses.A_NORMAL,
        }

    def run(self) -> None:
        curses.wrapper(self._main)

    def _main(self, stdscr: curses.window) -> None:
        try:
            curses.curs_set(1)
        except curses.error:
            pass

        stdscr.keypad(True)
        stdscr.timeout(100)
        self._init_colors()

        while self.running:
            self._draw(stdscr)
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue

            self._handle_key(stdscr, key)

    def _init_colors(self) -> None:
        if not curses.has_colors():
            return

        try:
            curses.start_color()
            curses.use_default_colors()

            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            curses.init_pair(3, curses.COLOR_MAGENTA, -1)
            curses.init_pair(4, curses.COLOR_BLUE, -1)
            curses.init_pair(5, curses.COLOR_GREEN, -1)
            curses.init_pair(6, curses.COLOR_WHITE, -1)
            curses.init_pair(7, curses.COLOR_RED, -1)

            self.attrs["header"] = curses.color_pair(1) | curses.A_BOLD
            self.attrs["status"] = curses.color_pair(6) | curses.A_DIM
            self.attrs["code"] = curses.color_pair(2)
            self.attrs["heading"] = curses.color_pair(3) | curses.A_BOLD
            self.attrs["user"] = curses.color_pair(4) | curses.A_BOLD
            self.attrs["assistant"] = curses.color_pair(5) | curses.A_BOLD
            self.attrs["system"] = curses.color_pair(6) | curses.A_BOLD
            self.attrs["error"] = curses.color_pair(7) | curses.A_BOLD
            self.attrs["tool"] = curses.color_pair(2)
        except curses.error:
            pass

    def _handle_key(self, stdscr: curses.window, key: object) -> None:
        if key == curses.KEY_PPAGE:
            self._scroll_page_up()
            return
        if key == curses.KEY_NPAGE:
            self._scroll_page_down()
            return
        if key == curses.KEY_UP and not self.input_buffer:
            self._scroll_lines(3)
            return
        if key == curses.KEY_DOWN and not self.input_buffer:
            self._scroll_lines(-3)
            return

        if isinstance(key, str):
            if key in ("\n", "\r"):
                self._submit(stdscr)
                return
            if key in ("\x08", "\x7f"):
                self.input_buffer = self.input_buffer[:-1]
                return
            if key == "\x03":
                self.running = False
                return
            if key.isprintable():
                self.input_buffer += key
                return

        if key in (curses.KEY_BACKSPACE, 127):
            self.input_buffer = self.input_buffer[:-1]

    def _submit(self, stdscr: curses.window) -> None:
        text = self.input_buffer.strip()
        self.input_buffer = ""

        if not text:
            return

        self.scroll_offset = 0

        if text.startswith("/"):
            self._handle_command(text)
            return

        if text.startswith("!"):
            self._add_message("user", text)
            self._run_one_shot_shell(text[1:])
            return

        self._add_message("user", text)
        self._ask_with_spinner(stdscr, text)

    def _run_one_shot_shell(self, command: str) -> None:
        self.status_text = "Running shell command..."
        ok, output = run_shell_command(command)
        self._add_message("system" if ok else "error", output)
        self.status_text = "Ready" if ok else "Shell command failed"

    def _handle_command(self, command: str) -> None:
        if command in ("/quit", "/exit"):
            self.running = False
            return

        if command == "/clear":
            self.session.clear_history()
            self.messages.clear()
            self.scroll_offset = 0
            self.status_text = "🧹 History cleared"
            return

        if command == "/clear_files":
            self.status_text = self.session.clear_attached_files()
            return

        if command == "/files":
            self._add_message("system", self.session.attached_files_text())
            self.status_text = "Ready"
            return

        if command == "/agent":
            state = "enabled" if self.session.is_agent_file_tools_enabled() else "disabled"
            self._add_message("system", f"🛠️ Agent file mode is {state}")
            self.status_text = "Ready"
            return

        if command == "/agent on":
            self.status_text = self.session.set_agent_file_tools_enabled(True)
            return

        if command == "/agent off":
            self.status_text = self.session.set_agent_file_tools_enabled(False)
            return

        if command == "/mode":
            current = self.session.get_agent_mode().upper()
            self._add_message("system", f"🧭 Current mode: {current}")
            self.status_text = "Ready"
            return

        if command == "/mode plan":
            self.status_text = self.session.set_agent_mode("plan")
            return

        if command == "/mode build":
            self.status_text = self.session.set_agent_mode("build")
            return

        if command == "/help":
            self._add_message(
                "system",
                "Commands:\n"
                "/clear - clear chat history\n"
                "/file <path> - attach a file\n"
                "/files - list attached files\n"
                "/clear_files - clear attached files\n"
                "/agent - show agent file mode status\n"
                "/agent on|off - toggle agent file mode\n"
                "/mode - show current mode\n"
                "/mode plan|build - set mode\n"
                "/quit - exit TUI\n"
                "!<command> - run one shell command\n"
                "PgUp/PgDn - scroll history\n"
                "PLAN mode: read-only tools (list/read/search/grep/diff_changes)\n"
                "BUILD mode: edit tools enabled (write_file/replace_in_file)",
            )
            self.status_text = "Ready"
            return

        if command == "/file":
            self._add_message("error", "❌ Usage: /file <path>")
            self.status_text = "Error"
            return

        if command.startswith("/file "):
            path = command[6:].strip()
            if not path:
                self._add_message("error", "❌ Usage: /file <path>")
                self.status_text = "Error"
                return

            ok, message = self.session.attach_file(path)
            self._add_message("system" if ok else "error", message)
            self.status_text = "Ready" if ok else "Error"
            return

        self._add_message("error", f"❌ Unknown command: {command}")
        self.status_text = "Error"

    def _ask_with_spinner(self, stdscr: curses.window, question: str) -> None:
        result: dict[str, object] = {}
        event_queue: queue.Queue[dict[str, str]] = queue.Queue()
        streamed_answer_index: int | None = None
        streamed_any_answer = False

        def worker() -> None:
            ok, answer = self.session.ask(question, on_event=event_queue.put)
            result["ok"] = ok
            result["answer"] = answer

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        dot_frames = [".", "..", "..."]
        idx = 0
        base_status = "Starting request..."

        while (thread.is_alive() or not event_queue.empty()) and self.running:
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    break

                event_type = event.get("type", "")
                text = event.get("text", "")

                if event_type == "status" and text:
                    base_status = text
                elif event_type == "tool" and text:
                    self._add_message("tool", text)
                    base_status = text
                elif event_type == "diff" and text:
                    self._add_message("tool", f"Diff:\n{text}")
                    base_status = "Diff ready"
                elif event_type == "final_start":
                    if streamed_answer_index is None:
                        self.messages.append(("assistant", ""))
                        streamed_answer_index = len(self.messages) - 1
                        streamed_any_answer = True
                        self.scroll_offset = 0
                elif event_type == "final_chunk":
                    if streamed_answer_index is None:
                        self.messages.append(("assistant", ""))
                        streamed_answer_index = len(self.messages) - 1
                        streamed_any_answer = True
                    role, current = self.messages[streamed_answer_index]
                    self.messages[streamed_answer_index] = (role, current + text)
                    self.scroll_offset = 0
                elif event_type == "final_end":
                    streamed_answer_index = None
                    base_status = "Finalizing..."

            self.status_text = f"{base_status} {dot_frames[idx % len(dot_frames)]}"
            idx = (idx + 1) % len(dot_frames)

            self._draw(stdscr)

            try:
                key = stdscr.get_wch()
                if key == curses.KEY_PPAGE:
                    self._scroll_page_up()
                elif key == curses.KEY_NPAGE:
                    self._scroll_page_down()
                elif isinstance(key, str) and key == "\x03":
                    self.running = False
                    break
            except curses.error:
                pass

            time.sleep(0.08)

        thread.join(timeout=0.1)

        ok = bool(result.get("ok"))
        answer = str(result.get("answer", "❌ Request finished without output"))
        if not streamed_any_answer:
            self._add_message("assistant" if ok else "error", answer)
        elif not ok:
            self._add_message("error", answer)
        self.status_text = "Ready" if ok else "Error"

    def _scroll_page_up(self) -> None:
        self._scroll_lines(max(1, self.last_chat_height // 2))

    def _scroll_page_down(self) -> None:
        self._scroll_lines(-max(1, self.last_chat_height // 2))

    def _scroll_lines(self, delta: int) -> None:
        self.scroll_offset = max(0, self.scroll_offset + delta)

    def _add_message(self, role: str, text: str) -> None:
        self.messages.append((role, text))
        self.scroll_offset = 0

    def _draw(self, stdscr: curses.window) -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()

        if height < 4 or width < 20:
            self._safe_addnstr(stdscr, 0, 0, "Terminal window is too small", width - 1, self.attrs["error"])
            stdscr.refresh()
            return

        header = (
            " AI Terminal TUI | Enter=send | !cmd=shell once | PgUp/PgDn=scroll "
            f"| mode={self.session.get_agent_mode().upper()} | files={self.session.attachments.count()} "
        )
        self._safe_addnstr(stdscr, 0, 0, header.ljust(width - 1), width - 1, self.attrs["header"])

        chat_start = 1
        status_y = height - 2
        input_y = height - 1
        chat_height = max(1, status_y - chat_start)
        self.last_chat_height = chat_height

        rows = self._build_chat_rows(max(1, width - 1))
        max_offset = max(0, len(rows) - chat_height)
        self.scroll_offset = min(self.scroll_offset, max_offset)

        end_index = len(rows) - self.scroll_offset
        start_index = max(0, end_index - chat_height)
        visible_rows = rows[start_index:end_index]

        for index, row in enumerate(visible_rows):
            self._draw_row(stdscr, chat_start + index, row, width - 1)

        status_line = self._effective_status_text(max_offset)
        self._safe_addnstr(stdscr, status_y, 0, status_line.ljust(width - 1), width - 1, self.attrs["status"])

        prompt = "> "
        available = max(1, width - len(prompt) - 1)
        input_view = self.input_buffer[-available:]
        input_line = f"{prompt}{input_view}"
        self._safe_addnstr(stdscr, input_y, 0, input_line.ljust(width - 1), width - 1, self.attrs["input"])

        cursor_x = min(width - 1, len(input_line))
        try:
            stdscr.move(input_y, cursor_x)
        except curses.error:
            pass

        stdscr.refresh()

    def _effective_status_text(self, max_offset: int) -> str:
        if self.input_buffer.startswith("/"):
            hint = self._command_hint(self.input_buffer)
            if hint:
                return hint

        if self.scroll_offset > 0:
            return f"{self.status_text} | scrolled +{self.scroll_offset}/{max_offset}"

        return self.status_text

    def _command_hint(self, current_input: str) -> str:
        query = current_input.strip()
        if not query.startswith("/"):
            return ""

        if " " in query:
            base = query.split(" ", 1)[0]
        else:
            base = query

        matches = []
        for command, description in self.COMMANDS:
            head = command.split(" ", 1)[0]
            if query == "/" or head.startswith(base):
                matches.append(f"{command} ({description})")

        if not matches:
            return "No matching slash command"

        return "Slash commands: " + " | ".join(matches[:4])

    def _build_chat_rows(self, width: int) -> list[list[StyledSpan]]:
        rows: list[list[StyledSpan]] = []
        for role, text in self.messages:
            rows.extend(self._render_message(role, text, width))
            rows.append([StyledSpan("", "normal")])
        return rows

    def _render_message(self, role: str, text: str, width: int) -> list[list[StyledSpan]]:
        prefix = self.ROLE_PREFIXES.get(role, "AI: ")
        role_style = role if role in self.attrs else "assistant"

        content_width = max(1, width - len(prefix))
        parsed_lines = markdown_to_styled_lines(text)

        wrapped: list[list[StyledSpan]] = []
        for parsed in parsed_lines:
            wrapped.extend(wrap_styled_line(parsed, content_width))

        if not wrapped:
            wrapped = [[StyledSpan("", "normal")]]

        result: list[list[StyledSpan]] = []
        for idx, line in enumerate(wrapped):
            leading = prefix if idx == 0 else " " * len(prefix)
            result.append([StyledSpan(leading, role_style), *line])

        return result

    def _draw_row(self, stdscr: curses.window, y: int, row: list[StyledSpan], width: int) -> None:
        x = 0
        for span in row:
            if x >= width:
                break
            text = span.text
            if not text:
                continue
            attr = self.attrs.get(span.style, self.attrs["normal"])
            self._safe_addnstr(stdscr, y, x, text, width - x, attr)
            x += len(text)

    @staticmethod
    def _safe_addnstr(
        stdscr: curses.window,
        y: int,
        x: int,
        text: str,
        max_len: int,
        attr: int,
    ) -> None:
        if max_len <= 0:
            return
        try:
            stdscr.addnstr(y, x, text, max_len, attr)
        except curses.error:
            pass
