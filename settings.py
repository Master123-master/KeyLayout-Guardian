"""
Settings persistence.

Stores configuration as JSON under %APPDATA%\\KeyLayoutGuardian. This keeps
the application portable (no registry footprint) and human-inspectable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "KeyLayoutGuardian"
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_FILE = _config_dir() / "settings.json"


@dataclass
class AppSettings:
    """User-persisted application state."""

    selected_langid: int | None = None
    protection_enabled: bool = False
    log_panel_expanded: bool = False

    @classmethod
    def load(cls) -> "AppSettings":
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return cls(
                selected_langid=data.get("selected_langid"),
                protection_enabled=bool(data.get("protection_enabled", False)),
                log_panel_expanded=bool(data.get("log_panel_expanded", False)),
            )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            # Fresh start or corrupt file -> sensible defaults.
            return cls()

    def save(self) -> None:
        try:
            CONFIG_FILE.write_text(
                json.dumps(asdict(self), indent=2), encoding="utf-8"
            )
        except OSError:
            # Persistence is best-effort; never crash on a failed write.
            pass
