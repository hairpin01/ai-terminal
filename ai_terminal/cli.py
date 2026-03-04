from __future__ import annotations

import argparse
import shutil
import sys

from .config import APIKeyMissingError, ConfigCreatedError, get_app_paths, load_config
from .formatting import render_markdown_ansi
from .session import ChatSession
from .shell import run_shell_command
from .tui import TerminalUI


def show_help() -> None:
    print("🤖 AI Terminal")
    print("\nUsage:")
    print("  ai-terminal [question]                  - Ask AI once")
    print("  ai-terminal -f files -p \"prompt\"       - Ask AI with attached files")
    print("  ai-terminal                             - Open TUI mode")
    print("  ai-terminal --no-tui                    - CLI only")
    print("  ai-terminal --mode plan|build           - Set agent mode for this run")
    print("  ai-terminal --config                    - Show config paths")
    print("  ai-terminal --clear/--reset             - Clear chat history")
    print("  ai-terminal --help                      - Show argparse help")
    print("\nTUI commands:")
    print("  /clear              - clear chat history")
    print("  /file <path>        - attach file")
    print("  /files              - list attached files")
    print("  /clear_files        - clear attached files")
    print("  /agent              - show agent file mode status")
    print("  /agent on|off       - toggle agent file mode")
    print("  /mode               - show current mode")
    print("  /mode plan|build    - set mode in current session")
    print("  /help               - show command help")
    print("  /quit               - exit TUI")
    print("\nOne-shot shell:")
    print("  !<command>          - run shell command once (CLI and TUI)")
    print("\nAgent file mode:")
    print("  AI can call local file tools (list/read/search/grep/edit/diff) automatically")
    print("  to inspect code before answering.")
    print("  TUI shows live tool actions and streamed final output; diff is auto-shown after edits.")
    print("\nTUI history scroll:")
    print("  PgUp/PgDn           - scroll chat history")
    print("\nConfig: ~/.config/ai-terminal.conf")


def _create_session() -> ChatSession:
    paths = get_app_paths()
    try:
        config = load_config(paths.config_file)
    except (ConfigCreatedError, APIKeyMissingError) as exc:
        print(exc)
        sys.exit(1)
    except Exception as exc:
        print(f"❌ Failed to load config: {exc}")
        sys.exit(1)

    try:
        return ChatSession(config, paths.history_file)
    except Exception as exc:
        print(f"❌ Failed to initialize AI client: {exc}")
        sys.exit(1)


def _clear_history_only() -> None:
    paths = get_app_paths()
    if paths.history_file.exists():
        paths.history_file.unlink()
        print("🧹 History cleared")
    else:
        print("ℹ️ History is already empty")


def _run_single_question(session: ChatSession, question: str) -> int:
    if question.startswith("!"):
        ok, output = run_shell_command(question[1:])
        print(output)
        return 0 if ok else 1

    ok, answer = session.ask(question)
    if not ok:
        print(answer)
        return 1

    if session.last_agent_actions:
        print("🛠️ Agent actions:")
        for action in session.last_agent_actions:
            print(f"  - {action}")

    if session.last_agent_diff:
        print("📄 Auto diff:")
        print(session.last_agent_diff)

    terminal_width = shutil.get_terminal_size((120, 40)).columns
    formatted = render_markdown_ansi(answer, width=max(20, terminal_width - 3))
    print(f"🤖 {formatted}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="🤖 AI Terminal - AI in your terminal")
    parser.add_argument("question", nargs="*", help="Question for AI")
    parser.add_argument("-f", "--files", help="Attach files (comma-separated)")
    parser.add_argument("-p", "--prompt", help="Prompt for AI")
    parser.add_argument("--config", action="store_true", help="Show config paths")
    parser.add_argument("--clear", "--reset", action="store_true", help="Clear chat history")
    parser.add_argument("--help-cmd", action="store_true", help="Show extended command help")
    parser.add_argument("--no-tui", action="store_true", help="Do not launch TUI")
    parser.add_argument("--mode", choices=["plan", "build"], help="Set agent mode for this run")

    args = parser.parse_args()
    paths = get_app_paths()

    if args.help_cmd:
        show_help()
        return

    if args.config:
        print(f"📁 Config: {paths.config_file}")
        print(f"📁 History: {paths.history_file}")
        return

    if args.clear:
        _clear_history_only()

    question = args.prompt if args.prompt else " ".join(args.question).strip()

    only_clear_requested = args.clear and not args.files and not question and not args.no_tui
    if only_clear_requested:
        return

    session = _create_session()
    if args.mode:
        print(session.set_agent_mode(args.mode))

    if args.files:
        for raw in args.files.split(","):
            file_path = raw.strip()
            if not file_path:
                continue
            ok, message = session.attach_file(file_path)
            print(message)
            if not ok:
                return

    if question:
        raise SystemExit(_run_single_question(session, question))

    if args.no_tui:
        show_help()
        return

    ui = TerminalUI(session)
    try:
        ui.run()
    except KeyboardInterrupt:
        print("\n👋 Bye")


if __name__ == "__main__":
    main()
