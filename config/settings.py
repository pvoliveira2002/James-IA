from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "assistant_name": "James",
    "ai_provider": "basic",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5:0.5b",
    "ollama_num_ctx": 4096,
    "ollama_num_predict": 512,
    "openai_model": "gpt-6-luna",
    "share_memories_with_openai": False,
    "context_max_messages": 12,
    "context_max_chars": 8000,
    "voice_input_enabled": False,
    "voice_output_enabled": False,
    "voice_model_path": "",
    "voice_input_device": None,
    "voice_sample_rate": 16000,
    "voice_rate": 175,
    "voice_volume": 1.0,
    "allowed_directories": [],
    "permissions": {
        "open_calculator": True,
        "open_notepad": True,
        "open_browser": True,
        "open_directory": True,
        "find_files": True,
        "organize_files": True,
        "system_info": True,
        "public_web_navigation": True,
        "browser_automation": True,
    },
}


class Settings:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.config_path = self.data_dir / "settings.json"
        self.database_path = self.data_dir / "james.db"
        self.log_path = self.data_dir / "james.log"
        self._data: dict[str, Any] = {}
        self.load()

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        self.ensure_directories()
        loaded: dict[str, Any] = {}
        if self.config_path.exists():
            try:
                loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = {}
        self._data = {**DEFAULTS, **loaded}
        self._data["permissions"] = {
            **DEFAULTS["permissions"], **loaded.get("permissions", {})
        }
        if not self.config_path.exists():
            self.save()

    def save(self) -> None:
        self.ensure_directories()
        self.config_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def permission(self, name: str) -> bool:
        return bool(self._data.get("permissions", {}).get(name, False))

    @property
    def allowed_directories(self) -> list[Path]:
        return [Path(p).resolve() for p in self.get("allowed_directories", [])]
