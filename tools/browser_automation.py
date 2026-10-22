from __future__ import annotations

import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from memory.database import Database
from tools.site_catalog import validate_public_url
from core.navigation_context import NavigationItem

T = TypeVar("T")


@dataclass(frozen=True)
class BrowserResult:
    success: bool
    title: str = ""
    url: str = ""
    details: str = ""


class BrowserAutomationService:
    """Mantem Playwright e Chrome numa unica thread e perfil exclusivo do James."""
    def __init__(self, profile_dir: Path, database: Database, timeout_ms: int = 15000):
        self.profile_dir, self.db, self.timeout_ms = Path(profile_dir), database, timeout_ms
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="james-browser")
        self._playwright = self._context = self._page = None
        self._stop = threading.Event()

    def _ensure(self):
        if self._page and not self._page.is_closed():
            return self._page
        from playwright.sync_api import sync_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir), channel="chrome", headless=False, no_viewport=True,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    def run(self, operation: Callable[[object], T], timeout: float = 65) -> T:
        return self._executor.submit(lambda: operation(self._ensure())).result(timeout=timeout)

    def open_url(self, url: str) -> BrowserResult:
        allowed, reason = validate_public_url(url)
        if not allowed:
            return BrowserResult(False, url=url, details=reason)
        self._stop.clear()
        def action(page):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                result = BrowserResult(True, page.title(), page.url, "Pagina aberta e verificada.")
            except Exception as exc:
                result = BrowserResult(False, url=url, details=f"Falha ao abrir a pagina: {exc}")
            self.db.log_navigation(result.url or url, result.title, "abrir", result.success, result.details)
            return result
        return self.run(action)

    def back(self) -> BrowserResult:
        def action(page):
            try:
                page.go_back(wait_until="domcontentloaded", timeout=self.timeout_ms)
                result = BrowserResult(True, page.title(), page.url, "Voltei para a pagina anterior.")
            except Exception as exc:
                result = BrowserResult(False, details=f"Nao foi possivel voltar: {exc}")
            self.db.log_navigation(result.url, result.title, "voltar", result.success, result.details)
            return result
        return self.run(action)

    def google_search(self, query: str, limit: int = 5) -> tuple[BrowserResult, list[NavigationItem]]:
        from urllib.parse import quote_plus, urljoin
        opened = self.open_url("https://www.google.com/search?q=" + quote_plus(query))
        if not opened.success: return opened, []
        def collect(page):
            try: page.locator("a:has(h3)").first.wait_for(state="attached", timeout=15000)
            except Exception: pass
            body = page.locator("body").inner_text(timeout=10000).casefold()
            if "unusual traffic" in body or "captcha" in body:
                raise RuntimeError("O Google solicitou verificação humana; o James não contorna CAPTCHA.")
            links, items, seen = page.locator("a:has(h3)"), [], set()
            for index in range(min(links.count(), 30)):
                try:
                    link = links.nth(index); href = urljoin("https://www.google.com", link.get_attribute("href") or "")
                    title = link.locator("h3").first.inner_text().strip()
                    allowed, _ = validate_public_url(href)
                    if title and allowed and href not in seen:
                        seen.add(href); items.append(NavigationItem(title, href))
                        if len(items) >= limit: break
                except Exception:
                    continue
            return items
        try:
            results = self.run(collect)
            if not results:
                return BrowserResult(False, opened.title, opened.url, "O Google abriu, mas não apresentou resultados públicos legíveis."), []
            return opened, results
        except Exception as exc:
            shot = self.screenshot("google_error")
            return BrowserResult(False, opened.title, opened.url, f"{exc}. Diagnóstico: {shot}"), []

    def visible_text(self, max_chars: int = 6000) -> BrowserResult:
        def action(page):
            try:
                text = page.locator("body").inner_text(timeout=self.timeout_ms).strip()[:max_chars]
                return BrowserResult(True, page.title(), page.url, text)
            except Exception as exc: return BrowserResult(False, details=f"Não foi possível ler a página: {exc}")
        return self.run(action)

    def screenshot(self, label: str = "diagnostic") -> str:
        directory = self.profile_dir.parent / "browser_diagnostics"; directory.mkdir(parents=True, exist_ok=True)
        safe = "".join(char for char in label if char.isalnum() or char in "_-")[:40] or "diagnostic"
        path = directory / f"{datetime.now():%Y%m%d_%H%M%S}_{safe}.png"
        try:
            self.run(lambda page: page.screenshot(path=str(path), full_page=False), timeout=20)
            return str(path)
        except Exception as exc: return f"captura indisponível ({exc})"

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def close(self) -> None:
        def action():
            if self._context: self._context.close()
            if self._playwright: self._playwright.stop()
        try: self._executor.submit(action).result(timeout=15)
        except Exception: pass
        self._executor.shutdown(wait=False, cancel_futures=True)
