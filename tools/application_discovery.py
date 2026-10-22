from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable
import winreg


BLOCKED_NAMES = {
    "cmd", "command prompt", "powershell", "windows powershell", "pwsh", "regedit",
    "registry editor", "wscript", "cscript", "mshta", "rundll32", "task scheduler",
    "services", "local security policy", "group policy editor", "uninstall",
    "agendador de tarefas", "ferramentas administrativas", "administrative tools",
}
IGNORED_PARTS = ("uninstall", "uninstaller", "unins", "installer", "update helper", "updater",
                 "crash reporter", "service host", "service", "daemon", "setup", "ajuda", " help")


def normalize_app_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    value = re.sub(r"\.(exe|lnk)$", "", value)
    value = re.sub(r"\s*\(\d+\)\s*$", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def is_safe_catalog_name(name: str) -> bool:
    normalized = normalize_app_name(name)
    return bool(normalized) and normalized not in BLOCKED_NAMES and not any(part in normalized for part in IGNORED_PARTS)


def is_web_application(name: str, target: str | None = None, app_id: str | None = None) -> bool:
    """Reconhece PWAs/atalhos web sem confundi-los com programas instalados nativos."""
    normalized_target = (target or "").replace("/", "\\").casefold()
    normalized_id = (app_id or "").casefold()
    return (normalized_id.startswith("chrome._crx_") or
            normalized_id.startswith("microsoft.microsoftedge.stable_") or
            "\\apps do chrome\\" in normalized_target or
            "\\chrome apps\\" in normalized_target or
            "\\web applications\\" in normalized_target)


@dataclass(frozen=True)
class DiscoveredApplication:
    id: str
    display_name: str
    normalized_name: str
    launch_target: str | None
    app_user_model_id: str | None
    app_type: str
    discovery_source: str
    icon_path: str | None = None

    def as_record(self) -> dict:
        return asdict(self)


def make_app_id(app_type: str, target: str, name: str) -> str:
    raw = f"{app_type}|{target.casefold()}|{normalize_app_name(name)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


class ApplicationDiscoveryService:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def discover(self) -> list[dict]:
        found: list[DiscoveredApplication] = []
        for source in (self._start_menu_shortcuts, self._app_paths, self._start_apps, self._path_apps):
            try: found.extend(source())
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError): continue
        return [item.as_record() for item in self._deduplicate(found)]

    def _start_menu_shortcuts(self) -> Iterable[DiscoveredApplication]:
        roots = [Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs"]
        for root in roots:
            if not root.is_dir(): continue
            for shortcut in root.rglob("*.lnk"):
                name = shortcut.stem
                if is_safe_catalog_name(name):
                    target = str(shortcut.resolve())
                    app_type = "web_app" if is_web_application(name, target=target) else "shortcut"
                    yield self._make(name, target, None, app_type, "start_menu")

    def _app_paths(self) -> Iterable[DiscoveredApplication]:
        locations = ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
                     (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"))
        for hive, location in locations:
            for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try: key = winreg.OpenKey(hive, location, 0, access)
                except OSError: continue
                with key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subname = winreg.EnumKey(key, index)
                            with winreg.OpenKey(key, subname) as subkey: target = str(winreg.QueryValue(subkey, None)).strip('"')
                            path = Path(target)
                            name = path.stem if path.name else Path(subname).stem
                            if path.is_file() and path.suffix.casefold() == ".exe" and is_safe_catalog_name(name):
                                yield self._make(name, str(path.resolve()), None, "win32", "app_paths")
                        except OSError: continue

    def _start_apps(self) -> Iterable[DiscoveredApplication]:
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                   "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout,
                                creationflags=flags, check=False, encoding="utf-8", errors="replace")
        if result.returncode or not result.stdout.strip(): return []
        data = json.loads(result.stdout); data = [data] if isinstance(data, dict) else data
        items = []
        for row in data:
            name, app_id = str(row.get("Name", "")).strip(), str(row.get("AppID", "")).strip()
            if name and app_id and is_safe_catalog_name(name):
                app_type = "web_app" if is_web_application(name, app_id=app_id) else "uwp"
                items.append(self._make(name, None, app_id, app_type, "get_start_apps"))
        return items

    def _path_apps(self) -> Iterable[DiscoveredApplication]:
        seen: set[str] = set()
        windows_root = Path(os.environ.get("WINDIR", r"C:\Windows")).resolve()
        for raw in os.environ.get("PATH", "").split(os.pathsep):
            directory = Path(raw.strip('"'))
            if not directory.is_dir(): continue
            try: directory.resolve().relative_to(windows_root); continue
            except ValueError: pass
            try: entries = directory.iterdir()
            except OSError: continue
            for path in entries:
                if path.suffix.casefold() != ".exe" or not path.is_file() or not self._is_gui_executable(path): continue
                name = path.stem
                if normalize_app_name(name) in seen or not is_safe_catalog_name(name): continue
                seen.add(normalize_app_name(name)); yield self._make(name, str(path.resolve()), None, "path", "path")

    @staticmethod
    def _is_gui_executable(path: Path) -> bool:
        """Lê somente campos do cabeçalho PE; 2 representa Windows GUI."""
        try:
            with path.open("rb") as stream:
                if stream.read(2) != b"MZ": return False
                stream.seek(0x3C); pe_offset = struct.unpack("<I", stream.read(4))[0]
                if pe_offset > 16 * 1024 * 1024: return False
                stream.seek(pe_offset)
                if stream.read(4) != b"PE\0\0": return False
                stream.seek(20, 1); optional_start = stream.tell()
                stream.seek(optional_start + 68)
                return struct.unpack("<H", stream.read(2))[0] == 2
        except (OSError, struct.error): return False

    @staticmethod
    def _make(name: str, target: str | None, app_id: str | None, app_type: str, source: str) -> DiscoveredApplication:
        identity = target or app_id or name
        return DiscoveredApplication(make_app_id(app_type, identity, name), name, normalize_app_name(name), target, app_id, app_type, source, target if target and target.lower().endswith(".exe") else None)

    @staticmethod
    def _deduplicate(items: Iterable[DiscoveredApplication]) -> list[DiscoveredApplication]:
        unique: dict[str, DiscoveredApplication] = {}
        priorities = {"app_paths": 4, "start_menu": 3, "get_start_apps": 2, "path": 1}
        for item in items:
            key = item.normalized_name
            existing = unique.get(key)
            if not existing or priorities.get(item.discovery_source, 0) > priorities.get(existing.discovery_source, 0): unique[key] = item
        return sorted(unique.values(), key=lambda app: app.display_name.casefold())
