import tempfile
import unittest
from pathlib import Path

from core.orchestrator import AgentOrchestrator
from memory.database import Database
from tools.browser_automation import BrowserResult
from tools.site_catalog import SiteCatalog, validate_public_url
from tools.youtube import VideoResult
from tools.default_browser import DefaultBrowserService
from core.navigation_context import NavigationItem
from core.navigation_intent import YouTubeAction, parse_youtube_intent


class FakeBrowser:
    stopped = False
    def open_url(self, url): return BrowserResult(True, "Pagina verificada", url, "ok")
    def back(self): return BrowserResult(True, "Resultados", "https://www.youtube.com/results", "Voltei para a pagina anterior.")
    def stop(self): self.stopped = True
    def google_search(self, query, limit=5):
        items = [NavigationItem(f"Fornecedor {i}", f"https://example{i}.com/") for i in range(1, limit + 1)]
        return BrowserResult(True, "Google", "https://www.google.com/search", "ok"), items
    def visible_text(self, max_chars=6000):
        return BrowserResult(True, "Fornecedor", "https://example1.com/", "Contato\nTelefone: 21 99999-0000\nE-mail: vendas@example.com")


class FakeDefaultBrowser:
    def __init__(self): self.urls = []
    def open(self, url, interpreted_command):
        from tools.default_browser import DefaultBrowserResult
        duplicate = url in self.urls
        if not duplicate: self.urls.append(url)
        detail = "A abertura já foi solicitada recentemente; evitei criar outra aba desnecessária." if duplicate else "A abertura foi solicitada ao navegador padrão; o carregamento da página não pôde ser verificado."
        return DefaultBrowserResult(True, url, "Fake padrão", detail, duplicate_avoided=duplicate)


class WebAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "test.db")
        self.browser = FakeBrowser()
        self.default_browser = FakeDefaultBrowser()
        self.agent = AgentOrchestrator(self.db, self.browser, default_browser=self.default_browser)

    def tearDown(self): self.temp.cleanup()

    def test_url_policy_blocks_unsafe_targets(self):
        self.assertTrue(validate_public_url("https://www.youtube.com/")[0])
        for url in ("file:///etc/passwd", "javascript:alert(1)", "http://localhost:8000", "https://127.0.0.1/", "https://192.168.1.2/"):
            self.assertFalse(validate_public_url(url)[0], url)

    def test_catalog_resolves_aliases(self):
        catalog = SiteCatalog(self.db)
        self.assertEqual(catalog.find("zap").name, "WhatsApp Web")
        self.assertEqual(catalog.find("youtube").url, "https://www.youtube.com/")

    def test_open_site_creates_verified_steps(self):
        reply = self.agent.handle("abra o YouTube")
        self.assertTrue(reply.handled); self.assertIn("abertura foi solicitada", reply.text)
        steps = self.db.automation_steps(reply.run_id)
        self.assertEqual([row["status"] for row in steps], ["concluido", "concluido"])

    def test_whatsapp_phrases_use_official_web_url(self):
        phrases = ("abra o WhatsApp Web.", "abra meu WhatsApp", "entre no WhatsApp pelo navegador", "quero acessar o WhatsApp Web")
        for phrase in phrases:
            reply = self.agent.handle(phrase)
            self.assertTrue(reply.handled, phrase)
            self.assertIn("WhatsApp Web", reply.text)
        self.assertEqual(self.default_browser.urls, ["https://web.whatsapp.com/"])

    def test_plain_whatsapp_is_reserved_for_desktop_application(self):
        self.assertFalse(self.agent.handle("abra o WhatsApp").handled)
        self.assertFalse(self.agent.handle("abra o aplicativo do WhatsApp").handled)
        self.assertTrue(self.agent.handle("abra o WhatsApp Web").handled)

    def test_google_and_youtube_use_default_browser_for_simple_open(self):
        self.agent.handle("abra o Google"); self.agent.handle("abra o YouTube")
        self.assertEqual(self.default_browser.urls, ["https://www.google.com/", "https://www.youtube.com/"])

    def test_default_browser_reports_missing_browser(self):
        def unavailable(_url): return False
        def failed_fallback(_url): raise OSError("nenhum aplicativo associado")
        service = DefaultBrowserService(self.db, opener=unavailable, fallback=failed_fallback)
        result = service.open("https://web.whatsapp.com/", "abra o WhatsApp Web")
        self.assertFalse(result.success); self.assertIn("Não foi possível", result.details)

    def test_youtube_results_and_contextual_selection(self):
        def search(_query):
            self.agent.youtube.last_results = [VideoResult("Caneca um", "https://www.youtube.com/watch?v=1"), VideoResult("Caneca dois", "https://www.youtube.com/watch?v=2")]
            return BrowserResult(True, "YouTube", "https://www.youtube.com/results", "ok"), self.agent.youtube.last_results
        self.agent.youtube.search = search
        reply = self.agent.handle("no YouTube procure como fazer canecas sublimadas")
        self.assertIn("2. Caneca dois", reply.text)
        chosen = self.agent.handle("abra o segundo")
        self.assertIn("Caneca dois", chosen.text)

    def test_compound_youtube_command_searches_and_opens_video(self):
        def search(_query):
            self.agent.youtube.last_results = [
                VideoResult("Como fazer blusa personalizada passo a passo", "https://www.youtube.com/watch?v=blusa"),
                VideoResult("Curso geral de costura", "https://www.youtube.com/watch?v=costura")]
            return BrowserResult(True, "YouTube", "https://www.youtube.com/results", "ok"), self.agent.youtube.last_results
        self.agent.youtube.search = search
        reply = self.agent.handle("Abra no YouTube um tutorial de blusa personalizada")
        self.assertIn("Como fazer blusa personalizada", reply.text)
        self.assertEqual(self.agent.context.current_url, "https://www.youtube.com/watch?v=blusa")
        self.assertNotEqual(self.agent.context.current_url, "https://www.youtube.com/")

    def test_youtube_intent_types_and_query_extraction(self):
        opened = parse_youtube_intent("Abra o YouTube")
        searched = parse_youtube_intent("Pesquise tutoriais de blusas personalizadas no YouTube")
        compound = parse_youtube_intent("Abra no YouTube um tutoria de blusa personalizada")
        self.assertEqual(opened.action, YouTubeAction.OPEN_SITE)
        self.assertEqual(searched.action, YouTubeAction.SEARCH)
        self.assertEqual(searched.query, "tutoriais de blusas personalizadas")
        self.assertEqual(compound.action, YouTubeAction.SEARCH_AND_OPEN)
        self.assertEqual(compound.query, "tutoria de blusa personalizada")

    def test_natural_video_phrases_are_understood(self):
        phrases = ("Procura como fazer camisa personalizada", "Quero assistir uma aula de estamparia",
                   "Me mostra um vídeo ensinando sublimação", "Pesquisa no YouTube como personalizar camisetas",
                   "Coloca um tutorial de prensa térmica")
        self.assertTrue(all(parse_youtube_intent(phrase) for phrase in phrases))

    def test_search_and_open_falls_back_to_direct_results_without_playwright(self):
        self.agent.youtube.search = lambda query: (BrowserResult(False, details="Playwright indisponível"), [])
        reply = self.agent.handle("Abra no YouTube um tutorial de blusa personalizada")
        self.assertIn("Não consegui analisar", reply.text)
        self.assertIn("search_query=tutorial+de+blusa+personalizada", self.default_browser.urls[-1])

    def test_acceptance_context_lists_results_and_goes_back(self):
        def search(_query):
            self.agent.youtube.last_results = [VideoResult(f"Tutorial {i}", f"https://www.youtube.com/watch?v={i}") for i in range(1, 6)]
            return BrowserResult(True, "YouTube", "https://www.youtube.com/results", "ok"), self.agent.youtube.last_results
        self.agent.youtube.search = search
        searched = self.agent.handle("pesquise tutoriais de canecas sublimadas no YouTube")
        self.assertIn("Tutorial 5", searched.text)
        listed = self.agent.handle("mostre os cinco primeiros resultados")
        self.assertIn("https://www.youtube.com/watch?v=5", listed.text)
        returned = self.agent.handle("volte para a pesquisa")
        self.assertIn("Tutorial 1", returned.text)
        self.assertEqual(self.agent.context.current_query, "tutoriais de canecas sublimadas")

    def test_google_search_returns_real_shaped_sources(self):
        reply = self.agent.handle("abra o Google e procure fornecedores de papel fotográfico")
        self.assertTrue(reply.handled); self.assertIn("Fornecedor 1", reply.text)
        self.assertIn("https://example1.com/", reply.text)
        self.assertEqual(self.agent.context.current_site, "Google")

    def test_reads_public_contact_information_from_current_page(self):
        self.agent.context.current_url = "https://example1.com/"
        reply = self.agent.handle("entre nesse site e procure as informações de contato")
        self.assertIn("Telefone", reply.text); self.assertIn("https://example1.com/", reply.text)

    def test_epsons_request_is_restricted_to_official_domain(self):
        captured = {}
        def search(query, limit=5):
            captured["query"] = query
            return BrowserResult(True, "Google", "https://www.google.com/search", "ok"), [NavigationItem("L3250", "https://epson.com.br/l3250")]
        self.browser.google_search = search
        reply = self.agent.handle("abra o site da Epson e procure informações sobre a L3250")
        self.assertIn("L3250", reply.text); self.assertIn("site:epson.com.br", captured["query"])

    def test_unavailable_intelligent_page_is_reported(self):
        self.browser.google_search = lambda query, limit=5: (BrowserResult(False, details="Página indisponível"), [])
        reply = self.agent.handle("procure fornecedores na internet")
        self.assertIn("indisponível", reply.text); self.assertEqual(self.agent.context.status, "erro")

    def test_stop_is_forwarded(self):
        self.agent.stop(); self.assertTrue(self.browser.stopped)


if __name__ == "__main__": unittest.main()
