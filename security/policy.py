from __future__ import annotations

from pathlib import Path
from config.settings import Settings


class SecurityPolicy:
    def __init__(self, settings: Settings):
        self.settings = settings

    def require_permission(self, tool: str) -> tuple[bool, str]:
        if self.settings.permission(tool):
            return True, ""
        return False, f"A ferramenta '{tool}' está desativada nas permissões."

    def validate_directory(self, path: Path) -> tuple[bool, str]:
        candidate = path.expanduser().resolve()
        allowed = self.settings.allowed_directories
        if not allowed:
            return False, "Nenhum diretório autorizado. Adicione um nas Configurações."
        for root in allowed:
            try:
                candidate.relative_to(root)
                return True, ""
            except ValueError:
                continue
        return False, "O diretório está fora das pastas autorizadas."
