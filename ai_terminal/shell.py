from __future__ import annotations

import subprocess


def run_shell_command(command: str, timeout: int = 60) -> tuple[bool, str]:
    cmd = command.strip()
    if not cmd:
        return False, "❌ Empty shell command. Use !<command>."

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"❌ Shell command timed out after {timeout}s: {cmd}"
    except Exception as exc:
        return False, f"❌ Failed to run shell command: {exc}"

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode == 0:
        body = stdout if stdout else "(no output)"
        return True, f"$ {cmd}\n{body}"

    details = []
    if stdout:
        details.append(stdout)
    if stderr:
        details.append(stderr)
    detail_text = "\n".join(details) if details else "(no output)"
    return False, f"$ {cmd}\n[exit code {result.returncode}]\n{detail_text}"
