from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode, urljoin

from tools.browser_automation import BrowserAutomationService, BrowserResult


@dataclass(frozen=True)
class VideoResult:
    title: str
    url: str


class YouTubeService:
    def __init__(self, browser: BrowserAutomationService):
        self.browser, self.last_results = browser, []

    def search(self, query: str, limit: int = 5) -> tuple[BrowserResult, list[VideoResult]]:
        url = "https://www.youtube.com/results?" + urlencode({"search_query": query})
        opened = self.browser.open_url(url)
        if not opened.success:
            return opened, []
        def collect(page):
            try:
                page.locator("a#video-title").first.wait_for(state="attached", timeout=20000)
            except Exception:
                pass
            text = page.locator("body").inner_text(timeout=10000).casefold()
            if "captcha" in text or "unusual traffic" in text:
                raise RuntimeError("O YouTube solicitou verificacao humana; o James nao contorna CAPTCHA.")
            locator = page.locator("a#video-title")
            results, seen = [], set()
            for index in range(min(locator.count(), 30)):
                item = locator.nth(index)
                title = (item.get_attribute("title") or item.inner_text()).strip()
                href = item.get_attribute("href") or ""
                full = urljoin("https://www.youtube.com", href)
                if title and "/watch?" in full and full not in seen:
                    seen.add(full); results.append(VideoResult(title, full))
                    if len(results) >= limit: break
            return results
        try:
            self.last_results = self.browser.run(collect)
            if not self.last_results:
                def reload(page):
                    page.reload(wait_until="domcontentloaded", timeout=20000); page.wait_for_timeout(2500)
                self.browser.run(reload)
                self.last_results = self.browser.run(collect)
            if not self.last_results:
                return BrowserResult(False, opened.title, opened.url, "O YouTube abriu, mas nao apresentou videos legiveis. Recarregue ou conclua uma verificacao visivel no navegador."), []
            return opened, self.last_results
        except Exception as exc:
            return BrowserResult(False, opened.title, opened.url, str(exc)), []

    def open_result(self, choice: int | str) -> BrowserResult:
        selected = None
        if isinstance(choice, int) and 1 <= choice <= len(self.last_results):
            selected = self.last_results[choice - 1]
        else:
            wanted = str(choice).casefold()
            selected = next((item for item in self.last_results if wanted in item.title.casefold()), None)
        if not selected:
            return BrowserResult(False, details="Nao encontrei essa opcao nos resultados recentes.")
        return self.browser.open_url(selected.url)
