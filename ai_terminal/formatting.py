from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StyledSpan:
    text: str
    style: str = "normal"


ANSI_RESET = "\033[0m"
ANSI_BY_STYLE = {
    "normal": "",
    "bold": "\033[1m",
    "italic": "\033[2m",
    "code": "\033[38;5;151m",
    "heading": "\033[1;36m",
    "muted": "\033[2m",
    "error": "\033[1;31m",
    "user": "\033[1;34m",
    "assistant": "\033[1;32m",
    "system": "\033[1;33m",
}


def _flush(buff: list[str], spans: list[StyledSpan], style: str = "normal") -> None:
    if buff:
        spans.append(StyledSpan("".join(buff), style))
        buff.clear()


def parse_inline_markdown(line: str) -> list[StyledSpan]:
    spans: list[StyledSpan] = []
    normal_buffer: list[str] = []

    i = 0
    while i < len(line):
        if line.startswith("**", i):
            end = line.find("**", i + 2)
            if end > i + 2:
                _flush(normal_buffer, spans)
                spans.append(StyledSpan(line[i + 2 : end], "bold"))
                i = end + 2
                continue

        if line[i] == "`":
            end = line.find("`", i + 1)
            if end > i + 1:
                _flush(normal_buffer, spans)
                spans.append(StyledSpan(line[i + 1 : end], "code"))
                i = end + 1
                continue

        if line[i] == "*":
            end = line.find("*", i + 1)
            if end > i + 1:
                _flush(normal_buffer, spans)
                spans.append(StyledSpan(line[i + 1 : end], "italic"))
                i = end + 1
                continue

        normal_buffer.append(line[i])
        i += 1

    _flush(normal_buffer, spans)
    return spans or [StyledSpan("", "normal")]


def markdown_to_styled_lines(text: str) -> list[list[StyledSpan]]:
    lines = text.splitlines() if text else [""]

    result: list[list[StyledSpan]] = []
    in_code_block = False

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            result.append([StyledSpan(raw, "code")])
            continue

        if raw.lstrip().startswith("#"):
            heading = raw.lstrip().lstrip("#").strip()
            result.append([StyledSpan(heading, "heading")])
            continue

        result.append(parse_inline_markdown(raw))

    return result or [[StyledSpan("", "normal")]]


def wrap_styled_line(spans: list[StyledSpan], width: int) -> list[list[StyledSpan]]:
    width = max(1, width)
    rows: list[list[StyledSpan]] = []
    current_row: list[StyledSpan] = []
    remaining = width

    if not spans:
        return [[StyledSpan("", "normal")]]

    for span in spans:
        text = span.text
        if text == "":
            continue

        while text:
            if remaining <= 0:
                rows.append(current_row)
                current_row = []
                remaining = width

            chunk = text[:remaining]
            current_row.append(StyledSpan(chunk, span.style))
            text = text[len(chunk) :]
            remaining -= len(chunk)

            if text:
                rows.append(current_row)
                current_row = []
                remaining = width

    if current_row:
        rows.append(current_row)

    if not rows:
        rows.append([StyledSpan("", "normal")])

    return rows


def _style_text(text: str, style: str) -> str:
    if not text:
        return ""
    ansi = ANSI_BY_STYLE.get(style, "")
    if not ansi:
        return text
    return f"{ansi}{text}{ANSI_RESET}"


def render_markdown_ansi(text: str, width: int | None = None) -> str:
    rendered: list[str] = []
    for line in markdown_to_styled_lines(text):
        rows = wrap_styled_line(line, width) if width else [line]
        for row in rows:
            rendered.append("".join(_style_text(span.text, span.style) for span in row))
    return "\n".join(rendered)
