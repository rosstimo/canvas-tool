from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanvasConfig:
    base_url: str
    api_token: str
    source: Path | None = None

    @property
    def origin(self) -> str:
        return self.base_url.rstrip("/")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _candidate_files() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("CANVAS_ENV_FILE")
    if explicit:
        candidates.append(Path(explicit).expanduser())

    root = os.environ.get("CANVAS_TOOL_ROOT")
    if root:
        candidates.append(Path(root) / ".env")

    candidates.append(Path.cwd() / ".env")

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "canvas-tool" / "config.env")
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        candidates.append(xdg / "canvas-tool" / "config.env")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def load_config() -> CanvasConfig:
    file_values: dict[str, str] = {}
    source: Path | None = None
    for path in _candidate_files():
        if path.is_file():
            file_values = _parse_env_file(path)
            source = path
            break

    base_url = os.environ.get("CANVAS_BASE_URL") or file_values.get("CANVAS_BASE_URL", "")
    token = os.environ.get("CANVAS_API_TOKEN") or file_values.get("CANVAS_API_TOKEN", "")

    if not base_url:
        raise ConfigError("CANVAS_BASE_URL is not configured")
    if not token:
        raise ConfigError("CANVAS_API_TOKEN is not configured")
    if not base_url.startswith("https://"):
        raise ConfigError("CANVAS_BASE_URL must use https://")

    return CanvasConfig(base_url=base_url.rstrip("/"), api_token=token, source=source)
