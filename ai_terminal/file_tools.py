from __future__ import annotations

import difflib
import fnmatch
import json
import os
import re
from pathlib import Path


class FileToolError(Exception):
    """Raised for file-tool execution errors."""


class FileToolExecutor:
    READ_TOOLS = {"list_files", "read_file", "search_files", "grep_files", "diff_changes"}
    WRITE_TOOLS = {"write_file", "replace_in_file"}

    def __init__(
        self,
        workspace_root: Path,
        mode: str = "plan",
        max_list_entries: int = 400,
        max_read_lines: int = 400,
        max_read_chars: int = 50000,
        max_search_results: int = 200,
        max_file_bytes: int = 1_000_000,
        max_scan_files: int = 2000,
        max_write_chars: int = 200000,
        max_diff_chars: int = 120000,
    ):
        self.workspace_root = workspace_root.resolve()
        self.mode = self._normalize_mode(mode)

        self.max_list_entries = max(1, max_list_entries)
        self.max_read_lines = max(1, max_read_lines)
        self.max_read_chars = max(1, max_read_chars)
        self.max_search_results = max(1, max_search_results)
        self.max_file_bytes = max(1, max_file_bytes)
        self.max_scan_files = max(1, max_scan_files)
        self.max_write_chars = max(1, max_write_chars)
        self.max_diff_chars = max(1, max_diff_chars)

        self._original_contents: dict[Path, str | None] = {}
        self._changed_paths: set[Path] = set()

    def openai_tools(self) -> list[dict]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files/directories in the workspace to discover project structure.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path relative to workspace root. Default: .",
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Whether to recurse into subdirectories. Default: true",
                            },
                            "max_entries": {
                                "type": "integer",
                                "description": "Requested max entries (capped by system limit).",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a text file from the workspace with optional line window.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path relative to workspace root.",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "1-based start line. Default: 1",
                            },
                            "max_lines": {
                                "type": "integer",
                                "description": "Requested number of lines (capped by system limit).",
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Search text in workspace files using a regex pattern.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Regex pattern to search for.",
                            },
                            "path": {
                                "type": "string",
                                "description": "Directory path relative to workspace root. Default: .",
                            },
                            "file_glob": {
                                "type": "string",
                                "description": "Glob pattern for files (e.g. *.py). Default: *",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Requested max results (capped by system limit).",
                            },
                        },
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep_files",
                    "description": (
                        "Grep-like search helper. If query has wildcards (*, ?, []), "
                        "it matches file names/paths. Otherwise it searches file content as regex."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Wildcard or regex query.",
                            },
                            "path": {
                                "type": "string",
                                "description": "Directory path relative to workspace root. Default: .",
                            },
                            "file_glob": {
                                "type": "string",
                                "description": "When content-searching, limit files by glob. Default: *",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Requested max results (capped by system limit).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "diff_changes",
                    "description": "Show unified diff of files changed through tool edits in current request.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]

        if self.mode == "build":
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "description": (
                                "Write full UTF-8 file content. Use for creating or replacing a file. "
                                "Prefer replace_in_file for small edits."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "File path relative to workspace root.",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "Full new file content.",
                                    },
                                },
                                "required": ["path", "content"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "replace_in_file",
                            "description": "Replace text in existing UTF-8 file. Good for targeted edits.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "File path relative to workspace root.",
                                    },
                                    "search": {
                                        "type": "string",
                                        "description": "Exact text to find.",
                                    },
                                    "replace": {
                                        "type": "string",
                                        "description": "Replacement text.",
                                    },
                                    "replace_all": {
                                        "type": "boolean",
                                        "description": "Replace all occurrences. Default: false",
                                    },
                                },
                                "required": ["path", "search", "replace"],
                            },
                        },
                    },
                ]
            )

        return tools

    def execute(self, tool_name: str, arguments: str) -> str:
        try:
            parsed = json.loads(arguments) if arguments else {}
            if not isinstance(parsed, dict):
                raise FileToolError("Arguments must be a JSON object")
        except json.JSONDecodeError as exc:
            return f"Tool error: invalid JSON arguments: {exc}"
        except FileToolError as exc:
            return f"Tool error: {exc}"

        normalized_name = (tool_name or "").strip()
        if normalized_name in self.WRITE_TOOLS and self.mode != "build":
            return "Tool error: write tools are disabled in plan mode"

        try:
            if normalized_name == "list_files":
                return self._list_files(
                    path=str(parsed.get("path", ".")),
                    recursive=bool(parsed.get("recursive", True)),
                    max_entries=int(parsed.get("max_entries", self.max_list_entries)),
                )
            if normalized_name == "read_file":
                return self._read_file(
                    path=str(parsed.get("path", "")),
                    start_line=int(parsed.get("start_line", 1)),
                    max_lines=int(parsed.get("max_lines", self.max_read_lines)),
                )
            if normalized_name == "search_files":
                return self._search_files(
                    pattern=str(parsed.get("pattern", "")),
                    path=str(parsed.get("path", ".")),
                    file_glob=str(parsed.get("file_glob", "*")),
                    max_results=int(parsed.get("max_results", self.max_search_results)),
                )
            if normalized_name == "grep_files":
                return self._grep_files(
                    query=str(parsed.get("query", "")),
                    path=str(parsed.get("path", ".")),
                    file_glob=str(parsed.get("file_glob", "*")),
                    max_results=int(parsed.get("max_results", self.max_search_results)),
                )
            if normalized_name == "write_file":
                return self._write_file(
                    path=str(parsed.get("path", "")),
                    content=str(parsed.get("content", "")),
                )
            if normalized_name == "replace_in_file":
                return self._replace_in_file(
                    path=str(parsed.get("path", "")),
                    search=str(parsed.get("search", "")),
                    replace=str(parsed.get("replace", "")),
                    replace_all=bool(parsed.get("replace_all", False)),
                )
            if normalized_name == "diff_changes":
                return self._diff_changes()

            return f"Tool error: unknown tool '{normalized_name}'"
        except FileToolError as exc:
            return f"Tool error: {exc}"
        except Exception as exc:
            return f"Tool error: unexpected failure: {exc}"

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        normalized = (mode or "").strip().lower()
        return "build" if normalized == "build" else "plan"

    def _resolve_path(self, raw_path: str) -> Path:
        if not raw_path:
            raise FileToolError("Path is required")

        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path

        resolved = path.resolve()
        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise FileToolError(
                f"Access denied outside workspace root: {self.workspace_root}"
            )

        return resolved

    def _to_workspace_relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace_root))
        except ValueError:
            return str(path)

    def _read_text_file(self, path: Path) -> str:
        if path.stat().st_size > self.max_file_bytes:
            raise FileToolError(
                f"File too large: {path.stat().st_size} bytes > limit {self.max_file_bytes}"
            )
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise FileToolError("File is not UTF-8 text")

    def _mark_before_change(self, path: Path) -> None:
        if path in self._original_contents:
            return

        if path.exists():
            if not path.is_file():
                raise FileToolError("Target path exists and is not a file")
            self._original_contents[path] = self._read_text_file(path)
        else:
            self._original_contents[path] = None

    def _list_files(self, path: str, recursive: bool, max_entries: int) -> str:
        target = self._resolve_path(path or ".")
        if not target.exists():
            raise FileToolError(f"Path not found: {path}")
        if not target.is_dir():
            raise FileToolError(f"Not a directory: {path}")

        limit = max(1, min(max_entries, self.max_list_entries))
        entries: list[str] = []

        if recursive:
            for root, dirnames, filenames in os.walk(target):
                dirnames.sort()
                filenames.sort()

                root_path = Path(root)
                if root_path != target:
                    entries.append(f"[D] {self._to_workspace_relative(root_path)}")
                    if len(entries) >= limit:
                        break

                for filename in filenames:
                    entries.append(
                        f"[F] {self._to_workspace_relative(root_path / filename)}"
                    )
                    if len(entries) >= limit:
                        break
                if len(entries) >= limit:
                    break
        else:
            for child in sorted(target.iterdir(), key=lambda x: x.name):
                marker = "[D]" if child.is_dir() else "[F]"
                entries.append(f"{marker} {self._to_workspace_relative(child)}")
                if len(entries) >= limit:
                    break

        truncated = len(entries) >= limit
        header = [
            f"workspace_root: {self.workspace_root}",
            f"listed_from: {self._to_workspace_relative(target)}",
            f"recursive: {str(recursive).lower()}",
            f"entry_count: {len(entries)}",
        ]
        if truncated:
            header.append("truncated: true")

        return "\n".join(header + ["", *entries])

    def _read_file(self, path: str, start_line: int, max_lines: int) -> str:
        target = self._resolve_path(path)
        if not target.exists():
            raise FileToolError(f"File not found: {path}")
        if not target.is_file():
            raise FileToolError(f"Not a file: {path}")

        text = self._read_text_file(target)
        lines = text.splitlines()
        total_lines = len(lines)

        start = max(1, start_line)
        line_limit = max(1, min(max_lines, self.max_read_lines))
        end = min(total_lines + 1, start + line_limit)

        selected: list[str] = []
        total_chars = 0
        for idx in range(start - 1, end - 1):
            numbered = f"{idx + 1:5d}: {lines[idx]}"
            if total_chars + len(numbered) + 1 > self.max_read_chars:
                break
            selected.append(numbered)
            total_chars += len(numbered) + 1

        truncated = (end - 1) < total_lines or (start - 1 + len(selected)) < (end - 1)

        header = [
            f"file: {self._to_workspace_relative(target)}",
            f"line_range: {start}-{start - 1 + len(selected)}",
            f"total_lines: {total_lines}",
            f"char_count: {total_chars}",
        ]
        if truncated:
            header.append("truncated: true")

        return "\n".join(header + ["", *selected])

    def _search_files(self, pattern: str, path: str, file_glob: str, max_results: int) -> str:
        if not pattern:
            raise FileToolError("Pattern is required")

        target_dir = self._resolve_path(path or ".")
        if not target_dir.exists():
            raise FileToolError(f"Path not found: {path}")
        if not target_dir.is_dir():
            raise FileToolError(f"Not a directory: {path}")

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise FileToolError(f"Invalid regex: {exc}")

        limit = max(1, min(max_results, self.max_search_results))

        results: list[str] = []
        scanned_files = 0

        for root, _, filenames in os.walk(target_dir):
            for filename in sorted(filenames):
                if not fnmatch.fnmatch(filename, file_glob):
                    continue

                file_path = Path(root) / filename
                scanned_files += 1
                if scanned_files > self.max_scan_files:
                    break

                try:
                    text = self._read_text_file(file_path)
                except Exception:
                    continue

                rel_path = self._to_workspace_relative(file_path)
                for line_no, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        snippet = line.strip()
                        if len(snippet) > 300:
                            snippet = snippet[:300] + "..."
                        results.append(f"{rel_path}:{line_no}: {snippet}")
                        if len(results) >= limit:
                            break

                if len(results) >= limit:
                    break
            if len(results) >= limit or scanned_files > self.max_scan_files:
                break

        header = [
            f"workspace_root: {self.workspace_root}",
            f"searched_from: {self._to_workspace_relative(target_dir)}",
            f"pattern: {pattern}",
            f"file_glob: {file_glob}",
            f"scanned_files: {min(scanned_files, self.max_scan_files)}",
            f"match_count: {len(results)}",
        ]
        if scanned_files > self.max_scan_files:
            header.append("scan_truncated: true")
        if len(results) >= limit:
            header.append("result_truncated: true")

        return "\n".join(header + ["", *results])

    def _grep_files(self, query: str, path: str, file_glob: str, max_results: int) -> str:
        if not query:
            raise FileToolError("Query is required")

        has_wildcards = any(token in query for token in ["*", "?", "["])
        target_dir = self._resolve_path(path or ".")
        if not target_dir.exists():
            raise FileToolError(f"Path not found: {path}")
        if not target_dir.is_dir():
            raise FileToolError(f"Not a directory: {path}")

        limit = max(1, min(max_results, self.max_search_results))

        if has_wildcards:
            matches: list[str] = []
            scanned_files = 0
            for root, _, filenames in os.walk(target_dir):
                for filename in sorted(filenames):
                    scanned_files += 1
                    if scanned_files > self.max_scan_files:
                        break
                    rel = self._to_workspace_relative(Path(root) / filename)
                    if fnmatch.fnmatch(filename, query) or fnmatch.fnmatch(rel, query):
                        matches.append(rel)
                        if len(matches) >= limit:
                            break
                if len(matches) >= limit or scanned_files > self.max_scan_files:
                    break

            header = [
                f"workspace_root: {self.workspace_root}",
                f"searched_from: {self._to_workspace_relative(target_dir)}",
                f"grep_mode: file_name_wildcard",
                f"query: {query}",
                f"scanned_files: {min(scanned_files, self.max_scan_files)}",
                f"match_count: {len(matches)}",
            ]
            if scanned_files > self.max_scan_files:
                header.append("scan_truncated: true")
            if len(matches) >= limit:
                header.append("result_truncated: true")

            results = [f"[F] {item}" for item in matches]
            return "\n".join(header + ["", *results])

        # Fallback to content search mode.
        return self._search_files(
            pattern=query,
            path=path,
            file_glob=file_glob,
            max_results=max_results,
        )

    def _write_file(self, path: str, content: str) -> str:
        if len(content) > self.max_write_chars:
            raise FileToolError(
                f"Content too large: {len(content)} chars > limit {self.max_write_chars}"
            )

        target = self._resolve_path(path)
        if target.exists() and not target.is_file():
            raise FileToolError("Target path exists and is not a file")

        target.parent.mkdir(parents=True, exist_ok=True)
        self._mark_before_change(target)
        target.write_text(content, encoding="utf-8")
        self._changed_paths.add(target)

        return (
            f"updated_file: {self._to_workspace_relative(target)}\n"
            f"new_char_count: {len(content)}"
        )

    def _replace_in_file(
        self,
        path: str,
        search: str,
        replace: str,
        replace_all: bool,
    ) -> str:
        if not search:
            raise FileToolError("'search' must be non-empty")

        target = self._resolve_path(path)
        if not target.exists():
            raise FileToolError(f"File not found: {path}")
        if not target.is_file():
            raise FileToolError(f"Not a file: {path}")

        original = self._read_text_file(target)
        if search not in original:
            raise FileToolError("Search text not found in file")

        self._mark_before_change(target)

        if replace_all:
            count = original.count(search)
            updated = original.replace(search, replace)
        else:
            count = 1
            updated = original.replace(search, replace, 1)

        if len(updated) > self.max_write_chars:
            raise FileToolError(
                f"Updated content too large: {len(updated)} chars > limit {self.max_write_chars}"
            )

        target.write_text(updated, encoding="utf-8")
        self._changed_paths.add(target)

        return (
            f"updated_file: {self._to_workspace_relative(target)}\n"
            f"replacements: {count}\n"
            f"new_char_count: {len(updated)}"
        )

    def _diff_changes(self) -> str:
        if not self._changed_paths:
            return "No file changes in this request"

        chunks: list[str] = []
        total_chars = 0

        for path in sorted(self._changed_paths, key=lambda p: self._to_workspace_relative(p)):
            before = self._original_contents.get(path)
            after = path.read_text(encoding="utf-8") if path.exists() else None

            before_lines = before.splitlines() if before is not None else []
            after_lines = after.splitlines() if after is not None else []

            rel = self._to_workspace_relative(path)
            diff_lines = list(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                    lineterm="",
                )
            )

            if not diff_lines:
                continue

            block = "\n".join(diff_lines)
            if total_chars + len(block) + 2 > self.max_diff_chars:
                remaining = self.max_diff_chars - total_chars
                if remaining > 0:
                    chunks.append(block[:remaining])
                chunks.append("\n[diff truncated]")
                break

            chunks.append(block)
            total_chars += len(block) + 2

        if not chunks:
            return "No net file changes to show"

        return "\n\n".join(chunks)

    def has_changes(self) -> bool:
        return bool(self._changed_paths)

    def get_changes_diff(self) -> str:
        return self._diff_changes()
