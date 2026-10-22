from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote_plus, urlencode

from memory.database import Database
from tools.browser_automation import BrowserAutomationService
from tools.site_catalog import SiteCatalog, normalize_site_name
from tools.youtube import YouTubeService
from tools.default_browser import DefaultBrowserService
from core.navigation_context import NavigationContext, NavigationItem
from core.navigation_intent import YouTubeAction, parse_youtube_intent


@dataclass(frozen=True)
class AutomationReply:
    handled: bool
    text: str = ""
    run_id: int | None = None


class AgentOrchestrator:
    ORDINALS = {"primeiro": 1, "primeira": 1, "segundo": 2, "segunda": 2, "terceiro": 3, "terceira": 3, "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5}
    def __init__(self, database: Database, browser: BrowserAutomationService, max_steps: int = 6, max_seconds: int = 90,
                 default_browser: DefaultBrowserService | None = None):
        self.db, self.browser = database, browser
        self.catalog, self.youtube = SiteCatalog(database), YouTubeService(browser)
        self.default_browser = default_browser or DefaultBrowserService(database)
        self.context = NavigationContext()
        self.max_steps, self.max_seconds = max_steps, max_seconds
        self._cancel = threading.Event(); self.current_run_id = None

    def stop(self) -> None:
        self._cancel.set(); self.browser.stop(); self.context.status = "cancelado"; self.context.current_step = "Interrompida pelo usuário"

    def handle(self, text: str) -> AutomationReply:
        low = text.casefold().strip(); started = time.monotonic()
        if re.search(r"\b(mostre|listar?|exiba)\b.*\b(resultados?|primeiros?)\b", low) and self.context.results:
            return AutomationReply(True, self._format_results(self.context.results[:5]))
        if re.search(r"\b(contato|telefone|e-?mail|endereço|endereco)\b", low) and self.context.current_url:
            read = self.browser.visible_text()
            if not read.success:
                self.context.fail(read.details); return AutomationReply(True, read.details)
            keywords = ("contato", "telefone", "whatsapp", "e-mail", "email", "endereço", "endereco")
            lines = [line.strip() for line in read.details.splitlines() if any(key in line.casefold() for key in keywords)]
            excerpt = "\n".join(dict.fromkeys(lines[:12]))
            self.context.current_step = "Informações públicas de contato lidas"
            return AutomationReply(True, (f"Informações visíveis em {read.url}:\n{excerpt}" if excerpt else
                                         f"Não encontrei informações de contato no texto visível de {read.url}."))
        if self._is_whatsapp_web_request(low):
            site = self.catalog.find("whatsapp web")
            return self._open_default_run(text, site.url, "Abrir WhatsApp Web")
        if re.search(r"\b(procure|pesquise)\b.*\b(mais recente|recentes?)\b", low) and self.context.current_query:
            return self._youtube_run(text, self.context.current_query + " mais recente", started)
        if re.search(r"\b(procure|pesquise|busque)\b.*\boutro\b", low) and self.context.current_query:
            return self._youtube_run(text, self.context.current_query + " outro tutorial", started)
        youtube_intent = parse_youtube_intent(low)
        if youtube_intent:
            if youtube_intent.action == YouTubeAction.OPEN_SITE:
                site = self.catalog.find("youtube")
                return self._open_default_run(text, site.url, "Abrir YouTube")
            if youtube_intent.action == YouTubeAction.SEARCH_AND_OPEN:
                return self._youtube_search_and_open(text, youtube_intent.query, started)
            return self._youtube_run(text, youtube_intent.query, started)
        if re.search(r"\b(volte|voltar|pagina anterior)\b", low):
            result = self.browser.back()
            if result.success:
                self.context.status, self.context.current_step = "concluido", "Retorno à página anterior"
                text_result = result.details
                if "pesquisa" in low and self.context.results: text_result += "\n" + self._format_results(self.context.results)
                return AutomationReply(True, text_result)
            self.context.fail(result.details); return AutomationReply(True, result.details)
        choice = re.search(r"\b(?:abra|abre|abrir|coloca|coloque)\s+(?:o\s+)?(primeiro|segundo|terceiro|quarto|quinto|[1-5])\b", low)
        if choice and self.youtube.last_results and self.context.current_site == "YouTube":
            raw = choice.group(1); number = int(raw) if raw.isdigit() else self.ORDINALS[raw]
            selected_title = self.youtube.last_results[number-1].title
            result = self.youtube.open_result(number)
            if result.success:
                self.context.current_url, self.context.current_step = result.url, f"Vídeo selecionado: {selected_title}"
            return AutomationReply(True, f"Video selecionado: {selected_title}" if result.success else result.details)
        if choice and self.context.results:
            raw = choice.group(1); number = int(raw) if raw.isdigit() else self.ORDINALS[raw]
            if number > len(self.context.results): return AutomationReply(True, "Esse resultado não existe na lista atual.")
            selected = self.context.results[number - 1]; result = self.browser.open_url(selected.url)
            if result.success:
                self.context.page_history.append(self.context.current_url); self.context.current_url = result.url
                self.context.current_step = f"Resultado aberto: {selected.title}"
            return AutomationReply(True, f"Resultado aberto: {selected.title}" if result.success else result.details)
        titled = re.search(r"\babra\b.*?\b(?:fala|sobre|título|titulo)\b\s+(.+)", low)
        if titled and self.youtube.last_results:
            result = self.youtube.open_result(titled.group(1).strip(" ."))
            return AutomationReply(True, f"Vídeo selecionado: {result.title}" if result.success else result.details)
        yt = re.search(r"(?:youtube.*?(?:procure|pesquise|buscar?|busque)|(?:procure|pesquise|buscar?|busque).*?youtube)(?:\s+(?:por|sobre))?\s+(.+)", low)
        if not yt:
            yt = re.search(r"(?:procure|pesquise|buscar?|busque)\s+(?:por\s+)?(.+?)\s+(?:no|na)\s+youtube", low)
        if not yt and re.search(r"\b(vídeos?|videos?|tutoriais?)\b", low):
            yt = re.search(r"(?:procure|pesquise|buscar?|busque|encontre)\s+(.+)", low)
        if yt:
            query = yt.group(1).strip(" .")
            return self._youtube_run(text, query, started)
        epson = re.search(r"(?:epson).*?(?:procure|pesquise|buscar?|busque)\s+(?:informações?\s+)?(?:sobre\s+)?(.+)", low)
        if epson:
            return self._google_run(text, "site:epson.com.br " + epson.group(1).strip(" ."))
        google = re.search(r"(?:abra|entre)(?:\s+o|\s+no)?\s+google\s+e\s+(?:procure|pesquise|busque)\s+(.+)", low)
        if not google:
            google = re.search(r"(?:pesquise|procure|busque|encontre)(?:\s+no google)?(?:\s+por|\s+sobre)?\s+(.+)", low)
        if google and ("google" in low or "internet" in low or "web" in low or "fornecedor" in low or "informações" in low or "informacoes" in low):
            return self._google_run(text, google.group(1).strip(" ."))
        opened = re.match(r"(?:abra|abre|abrir|acesse|ir para)\s+(?:o\s+|a\s+)?(.+?)[.!?]*$", low)
        if opened:
            requested = opened.group(1).strip()
            # "WhatsApp" sozinho significa o programa instalado. Somente pedidos
            # explicitamente Web seguem para o navegador.
            if re.fullmatch(r"(?:meu\s+)?(?:whatsapp|zap)", requested) and "meu " not in requested:
                return AutomationReply(False)
            site = self.catalog.find(requested)
            if site: return self._open_default_run(text, site.url, f"Abrir {site.name}")
        return AutomationReply(False)

    @staticmethod
    def _is_whatsapp_web_request(text: str) -> bool:
        if "whatsapp" not in text and not re.search(r"\bzap\b", text): return False
        action = re.search(r"\b(abra|abre|abrir|acesse|acessar|entre|entrar|quero)\b", text)
        web_context = "web" in text or "navegador" in text or "meu whatsapp" in text
        return bool(action and web_context)

    def _begin(self, objective: str, descriptions: list[str]):
        if len(descriptions) > self.max_steps: raise RuntimeError("Plano excede o limite seguro de etapas.")
        self._cancel.clear(); run_id = self.db.start_automation(objective); self.current_run_id = run_id
        return run_id, [self.db.add_automation_step(run_id, i+1, desc) for i, desc in enumerate(descriptions)]

    def _open_run(self, objective: str, url: str, description: str) -> AutomationReply:
        self.context.begin(objective, description.removeprefix("Abrir "))
        run_id, steps = self._begin(objective, [description, "Verificar pagina carregada"])
        self.db.update_automation_step(steps[0], "executando")
        result = self.browser.open_url(url)
        self.db.update_automation_step(steps[0], "concluido" if result.success else "erro", result.details)
        self.db.update_automation_step(steps[1], "concluido" if result.success and result.title else "erro", result.title or result.details)
        status = "concluido" if result.success else "erro"; self.db.finish_automation(run_id, status, result.title, "" if result.success else result.details)
        if result.success:
            self.context.current_url, self.context.status, self.context.current_step = result.url, "concluido", "Página carregada"
        else: self.context.fail(result.details)
        return AutomationReply(True, f"{description}: {result.title or result.details}", run_id)

    def _open_default_run(self, objective: str, url: str, description: str) -> AutomationReply:
        self.context.begin(objective, description.removeprefix("Abrir "))
        run_id, steps = self._begin(objective, [description, "Registrar solicitação ao navegador padrão"])
        self.db.update_automation_step(steps[0], "executando", f"Comando interpretado: {objective}; URL: {url}")
        result = self.default_browser.open(url, objective)
        state = "concluido" if result.success else "erro"
        self.db.update_automation_step(steps[0], state, result.details)
        verification = "Abertura solicitada; carregamento não verificável." if result.success else result.details
        self.db.update_automation_step(steps[1], state, verification)
        self.db.finish_automation(run_id, state, result.details if result.success else "", "" if result.success else result.details)
        self.context.current_url, self.context.status, self.context.current_step = url, state, "Abertura simples solicitada"
        if result.success and "whatsapp" in url:
            note = " Se aparecer um QR Code, vincule sua conta normalmente pelo celular."
        else: note = ""
        return AutomationReply(True, f"{description}: {result.details}{note}", run_id)

    def _youtube_run(self, objective: str, query: str, started: float) -> AutomationReply:
        self.context.begin(objective, "YouTube"); self.context.current_query = query
        run_id, steps = self._begin(objective, ["Abrir busca do YouTube", "Coletar resultados reais", "Apresentar ate cinco opcoes"])
        self.db.update_automation_step(steps[0], "executando")
        result, videos = self.youtube.search(query)
        elapsed_ok = time.monotonic() - started <= self.max_seconds and not self._cancel.is_set()
        ok = result.success and elapsed_ok
        self.db.update_automation_step(steps[0], "concluido" if ok else "erro", result.title or result.details)
        self.db.update_automation_step(steps[1], "concluido" if videos else "erro", f"{len(videos)} resultado(s)")
        self.db.update_automation_step(steps[2], "concluido" if videos else "erro", "Lista apresentada" if videos else result.details)
        if not videos:
            error = result.details or "Nenhum video encontrado."; self.db.finish_automation(run_id, "erro", "", error)
            self.context.fail(error)
            return AutomationReply(True, error, run_id)
        listing = "\n".join(f"{i}. {video.title}" for i, video in enumerate(videos, 1))
        text = f"Encontrei estes resultados reais no YouTube:\n{listing}\n\nDiga, por exemplo, 'abra o segundo'."
        self.db.finish_automation(run_id, "concluido", text)
        self.context.update_results(query, [NavigationItem(v.title, v.url) for v in videos], result.url)
        return AutomationReply(True, text, run_id)

    def _youtube_search_and_open(self, objective: str, query: str, started: float) -> AutomationReply:
        searched = self._youtube_run(objective, query, started)
        videos = self.youtube.last_results
        if not videos:
            # Pesquisa direta continua disponível mesmo quando o Playwright/site falha.
            url = "https://www.youtube.com/results?" + urlencode({"search_query": query})
            fallback = self.default_browser.open(url, objective)
            return AutomationReply(True, f"Não consegui analisar vídeos automaticamente. {fallback.details}", searched.run_id)
        stop = {"de", "da", "do", "das", "dos", "um", "uma", "como", "fazer", "tutorial", "tutoria", "aula", "video"}
        wanted = {word for word in re.findall(r"[a-z0-9]+", query.casefold()) if word not in stop and len(word) > 2}
        synonyms = {"blusa": {"camisa", "camiseta", "estampa"}, "personalizada": {"personalizado", "personalizar", "estampa"},
                    "camisa": {"blusa", "camiseta"}, "camiseta": {"blusa", "camisa"}}
        wanted |= {term for word in tuple(wanted) for term in synonyms.get(word, set())}
        scored = []
        for index, video in enumerate(videos):
            title_words = set(normalize_site_name(video.title).split())
            score = len(wanted & title_words) / max(1, len(wanted))
            scored.append((score, -index, video))
        scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
        best_score, _, best = scored[0]
        if wanted and best_score == 0 and len(videos) > 1:
            return AutomationReply(True, searched.text + "\n\nNão identifiquei uma opção claramente relacionada. Escolha pelo número.", searched.run_id)
        opened = self.youtube.open_result(best.title)
        if not opened.success or "/watch?" not in opened.url:
            return AutomationReply(True, searched.text + f"\n\nEncontrei opções, mas não consegui confirmar a abertura do vídeo: {opened.details}", searched.run_id)
        self.context.current_url, self.context.current_step = opened.url, f"Vídeo aberto: {best.title}"
        return AutomationReply(True, f"Pesquisei por “{query}” e abri o vídeo real: {best.title}\n{opened.url}", searched.run_id)

    def _google_run(self, objective: str, query: str) -> AutomationReply:
        self.context.begin(objective, "Google"); self.context.current_query = query
        self.youtube.last_results = []
        run_id, steps = self._begin(objective, ["Pesquisar no Google", "Ler resultados públicos", "Apresentar fontes"])
        self.db.update_automation_step(steps[0], "executando", query)
        result, items = self.browser.google_search(query, 5)
        state = "concluido" if items else "erro"
        self.db.update_automation_step(steps[0], state, result.title or result.details)
        self.db.update_automation_step(steps[1], state, f"{len(items)} resultado(s) reais")
        self.db.update_automation_step(steps[2], state, "Links apresentados" if items else result.details)
        if not items:
            self.context.fail(result.details); self.db.finish_automation(run_id, "erro", "", result.details)
            return AutomationReply(True, result.details, run_id)
        self.context.update_results(query, items, result.url)
        text = "Resultados públicos encontrados no Google:\n" + self._format_results(items)
        self.db.finish_automation(run_id, "concluido", text)
        return AutomationReply(True, text, run_id)

    @staticmethod
    def _format_results(items: list[NavigationItem]) -> str:
        return "\n".join(f"{i}. {item.title}\n   {item.url}" for i, item in enumerate(items, 1))
