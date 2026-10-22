from __future__ import annotations

import os
import time
import webbrowser
from dataclasses import dataclass
from typing import Callable

from memory.database import Database
from tools.site_catalog import validate_public_url


@dataclass(frozen=True)
class DefaultBrowserResult:
    success: bool
    url: str
    browser: str
    details: str
    verified: bool = False
    duplicate_avoided: bool = False


class DefaultBrowserService:
    """Solicita URLs ao navegador padrão sem acessar cookies ou perfis do usuário."""
    def __init__(self, database: Database, opener: Callable[[str], bool] | None = None,
                 fallback: Callable[[str], object] | None = None, dedupe_seconds: float = 8.0):
        self.db = database
        self.opener = opener or webbrowser.open_new_tab
        self.fallback = fallback if fallback is not None else (os.startfile if os.name == "nt" else None)
        self.dedupe_seconds = dedupe_seconds
        self._last_open: dict[str, float] = {}

    @staticmethod
    def browser_name() -> str:
        try:
            controller = webbrowser.get()
            return getattr(controller, "name", "") or controller.__class__.__name__
        except webbrowser.Error:
            return "navegador padrão do Windows"

    def open(self, url: str, interpreted_command: str) -> DefaultBrowserResult:
        allowed, reason = validate_public_url(url)
        browser = self.browser_name()
        if not allowed:
            return self._record(False, url, browser, interpreted_command, reason)
        now = time.monotonic()
        if now - self._last_open.get(url, -self.dedupe_seconds) < self.dedupe_seconds:
            details = "A abertura já foi solicitada recentemente; evitei criar outra aba desnecessária."
            return self._record(True, url, browser, interpreted_command, details, duplicate=True)
        errors: list[str] = []
        try:
            requested = bool(self.opener(url))
            if requested:
                self._last_open[url] = now
                return self._record(True, url, browser, interpreted_command,
                                    "A abertura foi solicitada ao navegador padrão; o carregamento da página não pôde ser verificado.")
            errors.append("o navegador padrão recusou a solicitação")
        except Exception as exc:
            errors.append(f"webbrowser.open_new_tab: {exc}")
        if self.fallback:
            try:
                self.fallback(url); self._last_open[url] = now
                return self._record(True, url, "Windows Shell", interpreted_command,
                                    "A abertura foi solicitada pelo Windows; o carregamento da página não pôde ser verificado.")
            except Exception as exc:
                errors.append(f"alternativa do Windows: {exc}")
        return self._record(False, url, browser, interpreted_command,
                            "Não foi possível solicitar a abertura: " + "; ".join(errors))

    def _record(self, success: bool, url: str, browser: str, command: str, details: str,
                duplicate: bool = False) -> DefaultBrowserResult:
        diagnostic = f"comando={command!r}; url={url}; navegador={browser}; resultado={details}"
        self.db.log_navigation(url, "", "abrir_navegador_padrao", success, diagnostic)
        self.db.log_action("open_public_site", diagnostic, True, success)
        return DefaultBrowserResult(success, url, browser, details, False, duplicate)
