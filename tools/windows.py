from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path


def open_program(program: str) -> tuple[bool, str]:
    commands = {"calculator": "calc.exe", "notepad": "notepad.exe"}
    executable = commands.get(program)
    if not executable:
        return False, "Programa não reconhecido."
    try:
        subprocess.Popen([executable])
        return True, "Programa aberto."
    except OSError as exc:
        return False, f"Não foi possível abrir o programa: {exc}"


def open_browser() -> tuple[bool, str]:
    return (True, "Navegador aberto.") if webbrowser.open("about:blank") else (False, "Não encontrei um navegador padrão.")


def open_directory(path: Path) -> tuple[bool, str]:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return True, f"Pasta aberta: {path}"
    except OSError as exc:
        return False, f"Não foi possível abrir a pasta: {exc}"


def system_info() -> str:
    drive = Path.home().anchor
    usage = shutil.disk_usage(drive)
    return (f"Sistema: {platform.system()} {platform.release()} | Computador: {platform.node()} | "
            f"Processador: {platform.processor() or 'não identificado'} | "
            f"Espaço livre: {usage.free / (1024**3):.1f} GB")
