from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Base config error."""


class ConfigCreatedError(ConfigError):
    """Raised when config is created and requires manual setup."""


class APIKeyMissingError(ConfigError):
    """Raised when API key is missing in the config."""


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    config_file: Path
    history_file: Path


def get_app_paths() -> AppPaths:
    config_dir = Path.home() / ".config"
    return AppPaths(
        config_dir=config_dir,
        config_file=config_dir / "ai-terminal.conf",
        history_file=config_dir / "ai-terminal-history.json",
    )


def create_default_config(config_file: Path) -> None:
    config_file.parent.mkdir(parents=True, exist_ok=True)

    config = configparser.ConfigParser()
    config["api"] = {
        "base_url": "https://api.intelligence.io.solutions/api/v1/",
        "api_key": "YOUR_API_KEY_HERE",
        "model_name": "meta-llama/Llama-3.3-70B-Instruct",
    }
    config["settings"] = {
        "system_prompt": (
            "You are a helpful AI assistant. Reply clearly in English, keep markdown formatting, "
            "and preserve code blocks when present."
        ),
        "temperature": "0.7",
        "max_tokens": "4096",
        "memory_depth": "5",
        "agent_file_tools": "true",
        "agent_mode": "plan",
        "agent_stream_final": "true",
        "agent_max_steps": "16",
        "agent_list_max_entries": "1500",
        "agent_read_max_lines": "1200",
        "agent_read_max_chars": "200000",
        "agent_search_max_results": "1000",
        "agent_max_file_bytes": "1000000",
        "agent_max_scan_files": "10000",
        "agent_max_write_chars": "400000",
        "agent_max_diff_chars": "300000",
    }

    with config_file.open("w", encoding="utf-8") as fp:
        config.write(fp)


def load_config(config_file: Path) -> configparser.ConfigParser:
    if not config_file.exists():
        create_default_config(config_file)
        raise ConfigCreatedError(
            f"📁 Config created: {config_file}\n"
            "🔑 Set your API key in the config file"
        )

    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")

    api_key = config.get("api", "api_key", fallback="YOUR_API_KEY_HERE")
    if api_key == "YOUR_API_KEY_HERE":
        raise APIKeyMissingError("❌ Set your API key in the config file")

    return config
