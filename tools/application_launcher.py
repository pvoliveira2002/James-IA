from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

from memory.database import Database
from tools.application_discovery import BLOCKED_NAMES, normalize_app_name


class ApplicationLauncherService:
    def __init__(self, database: Database, popen: Callable = subprocess.Popen):
        self.db, self.popen = database, popen

    def launch(self, app_id: str) -> tuple[bool, str]:
        app = self.db.get_application(app_id)
        if not app: return False, "Aplicativo não encontrado ou indisponível no catálogo."
        if self.db.application_permission(app_id) != "allow": return False, "A abertura deste aplicativo ainda não foi autorizada."
        try:
            verified = self._validate_and_launch(app)
            message = (f"Aplicativo iniciado e processo verificado: {app['display_name']}" if verified else
                       f"Solicitação de abertura enviada: {app['display_name']}. A janela ainda não pôde ser verificada.")
            self.db.log_application_launch(app_id, True, message); return True, message
        except (OSError, ValueError) as exc:
            message = f"Não foi possível abrir {app['display_name']}: {exc}"
            self.db.log_application_launch(app_id, False, message); return False, message

    def _validate_and_launch(self, app) -> bool:
        if normalize_app_name(app["display_name"]) in BLOCKED_NAMES: raise ValueError("aplicativo sensível bloqueado pela política")
        app_type = app["app_type"]
        if app_type == "web_app":
            raise ValueError("este item é um site/PWA; peça explicitamente a versão Web")
        if app_type == "uwp":
            app_user_id = str(app["app_user_model_id"] or "")
            if not app_user_id or any(char in app_user_id for char in "\r\n;&|"): raise ValueError("identificador de aplicativo inválido")
            self.popen(["explorer.exe", f"shell:AppsFolder\\{app_user_id}"], shell=False); return False
        target = Path(str(app["launch_target"] or "")).resolve(strict=True)
        if app_type == "shortcut":
            if target.suffix.casefold() != ".lnk": raise ValueError("atalho inválido")
            os.startfile(str(target)); return False  # type: ignore[attr-defined]
        if app_type in {"win32", "path", "portable"}:
            if target.suffix.casefold() != ".exe": raise ValueError("somente executáveis .exe são permitidos")
            process = self.popen([str(target)], shell=False)
            try: return process.poll() is None
            except AttributeError: return False
        raise ValueError("tipo de aplicativo não permitido")
