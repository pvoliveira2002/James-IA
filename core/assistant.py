from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ai.base import ProviderResponse, ToolCall
from ai.ollama import OllamaProvider
from ai.openai_provider import OpenAIProvider
from config.settings import Settings
from core.context import ConversationContext
from core.router import Intent, IntentRouter
from memory.database import Database
from security.policy import SecurityPolicy
from tools import windows
from tools.application_launcher import ApplicationLauncherService
from tools.application_matcher import ApplicationMatcher
from tools.application_discovery import normalize_app_name
from tools.browser_automation import BrowserAutomationService
from core.orchestrator import AgentOrchestrator


@dataclass
class AssistantResponse:
    text: str
    action: str | None = None
    payload: object | None = None


class Assistant:
    def __init__(self, database: Database, settings: Settings,
                 provider_factory: Callable[[str], object] | None = None):
        self.db = database
        self.settings = settings
        self.policy = SecurityPolicy(settings)
        self.router = IntentRouter()
        self.context = ConversationContext(
            database, int(settings.get("context_max_messages", 12)),
            int(settings.get("context_max_chars", 8000)))
        self.provider_factory = provider_factory
        self._last_provider_status: dict[str, tuple[bool, str]] = {}
        self.app_matcher = ApplicationMatcher(database)
        self.app_launcher = ApplicationLauncherService(database)
        self.browser = BrowserAutomationService(settings.data_dir / "browser_profile", database)
        self.orchestrator = AgentOrchestrator(database, self.browser)

    def process(self, original: str) -> AssistantResponse:
        text = original.strip()
        clean = re.sub(r"^(james|jarvis)[,\s:]+", "", text, flags=re.I).strip()
        low = clean.casefold()
        if not clean:
            return AssistantResponse("Digite um comando para eu ajudar.")
        if self.settings.permission("public_web_navigation") and self.settings.permission("browser_automation"):
            navigation = self.orchestrator.handle(clean)
            if navigation.handled:
                return AssistantResponse(navigation.text, action="refresh_automations", payload=navigation.run_id)
        intent = self.router.classify(clean)
        if re.search(r"\b(ajuda|comandos)\b", low):
            return AssistantResponse(self.help_text())
        if "calculadora" in low and re.search(r"\b(abra|abrir|inicie)\b", low):
            return self._run_tool("open_calculator", "Abrindo a calculadora.", lambda: windows.open_program("calculator"))
        if ("bloco de notas" in low or "notepad" in low) and re.search(r"\b(abra|abrir|inicie)\b", low):
            return self._run_tool("open_notepad", "Abrindo o Bloco de Notas.", lambda: windows.open_program("notepad"))
        if "navegador" in low and re.search(r"\b(abra|abrir|inicie)\b", low):
            return self._run_tool("open_browser", "Abrindo o navegador.", windows.open_browser)
        folder_match = re.match(r"(?:abra|abrir) (?:minha |a )?pasta(?: de)?\s+(.+)", clean, re.I)
        if folder_match:
            allowed, reason = self.policy.require_permission("open_directory")
            if not allowed:
                return AssistantResponse(reason)
            wanted = folder_match.group(1).strip().casefold()
            matches = [p for p in self.settings.allowed_directories
                       if wanted in p.name.casefold() or wanted in str(p).casefold()]
            if not matches:
                return AssistantResponse("Não encontrei essa pasta entre os diretórios autorizados nas Configurações.")
            success, details = windows.open_directory(matches[0])
            self.db.log_action("open_directory", str(matches[0]), True, success)
            return AssistantResponse(details)
        if "informações do computador" in low or "informacoes do computador" in low or "sistema" == low:
            allowed, reason = self.policy.require_permission("system_info")
            return AssistantResponse(windows.system_info() if allowed else reason)
        task_match = re.match(r"(?:adicione|crie|cadastrar?|nova) (?:uma )?tarefa[: ]+(.+)", clean, re.I)
        if task_match:
            title = task_match.group(1).strip()
            self.db.add_task(title)
            return AssistantResponse(f"Tarefa cadastrada: {title}", action="refresh_tasks")
        if "tarefas" in low and re.search(r"\b(mostre|listar?|quais|consultar?)\b", low):
            tasks = self.db.tasks()
            if not tasks:
                return AssistantResponse("Você não possui tarefas pendentes.")
            return AssistantResponse("Tarefas pendentes:\n" + "\n".join(f"• #{row['id']} {row['title']}" for row in tasks))
        memory_match = re.match(r"(?:lembre|memorize|guarde)(?: que)?[: ]+(.+)", clean, re.I)
        if memory_match:
            content = memory_match.group(1).strip()
            self.db.add_memory(content)
            return AssistantResponse(f"Informação guardada: {content}", action="refresh_memories")
        if re.search(r"\b(o que você lembra|memórias|memorias)\b", low):
            memories = self.db.memories()
            return AssistantResponse("Ainda não há memórias cadastradas." if not memories else
                                     "Memórias:\n" + "\n".join(f"• #{m['id']} {m['content']}" for m in memories[:20]))
        if re.search(r"\b(organize|organizar)\b", low) and re.search(r"\b(arquivos?|documentos?|pasta)\b", low):
            return AssistantResponse("Escolha uma pasta autorizada para visualizar a organização.", action="organize")
        if re.search(r"\b(procure|localize|buscar arquivo)\b", low):
            query = re.sub(r"^(procure|localize)(?: (?:o|a|os|as))?\s*", "", clean, flags=re.I).strip()
            return AssistantResponse("Escolha onde pesquisar.", action="find", payload=query)
        if re.search(r"\b(oi|olá|ola|bom dia|boa tarde|boa noite)\b", low):
            count = len(self.db.tasks())
            greeting = "Bom dia" if datetime.now().hour < 12 else "Boa tarde" if datetime.now().hour < 18 else "Boa noite"
            return AssistantResponse(f"{greeting}! Estou pronto. Você possui {count} tarefa(s) pendente(s).")
        alias_match = re.search(r"quando eu falar\s+(.+?),?\s+(?:eu )?quero que (?:você )?(?:abra|inicie)\s+(.+)", clean, re.I)
        if alias_match:
            alias, target = alias_match.group(1).strip(), alias_match.group(2).strip(" .")
            matches = self.app_matcher.match(target)
            if len(matches) == 1:
                self.db.set_application_alias(matches[0].app_id, alias, normalize_app_name(alias))
                return AssistantResponse(f"Entendido. Quando você disser “{alias}”, vou localizar {matches[0].display_name}.", action="refresh_app_view")
            return AssistantResponse("Não consegui identificar um único aplicativo para esse apelido. Informe o nome exato exibido no catálogo.")
        app_query = self._application_query(clean)
        if app_query:
            return self.request_application(app_query)
        # Tudo que não foi resolvido localmente segue para o provedor, inclusive
        # pedidos ambíguos de ação, para que ele possa esclarecer ou pedir uma ferramenta.
        return self._conversation(clean, intent)

    def _conversation(self, clean: str, intent: Intent) -> AssistantResponse:
        provider_name = str(self.settings.get("ai_provider", "basic"))
        if provider_name == "basic":
            return AssistantResponse(
                "A conversação inteligente está indisponível no modo Básico. "
                "Os comandos locais continuam funcionando; escolha Ollama ou OpenAI nas Configurações para conversar naturalmente."
            )
        messages = self.context.recent_messages()
        if not messages or messages[-1].get("content") != clean:
            messages.append({"role": "user", "content": clean})
        memories: list[str] = []
        if provider_name == "ollama" or bool(self.settings.get("share_memories_with_openai", False)):
            memories = self.context.authorized_memories()
        instructions = self._instructions(memories, provider_name, intent)
        try:
            provider = self._provider(provider_name)
            if provider_name == "ollama" and not provider.available():  # type: ignore[attr-defined]
                self._last_provider_status[provider_name] = (False, "desconectado")
                return AssistantResponse("O Ollama está desconectado. Inicie o serviço ou selecione outro provedor nas Configurações.")
            result: ProviderResponse = provider.chat(messages, instructions)  # type: ignore[attr-defined]
            self._last_provider_status[provider_name] = (True, "conectado")
        except RuntimeError as exc:
            self._last_provider_status[provider_name] = (False, "indisponível")
            return AssistantResponse(str(exc))
        if result.tool_calls:
            call = result.tool_calls[0]
            if call.name not in self._tool_descriptions():
                return AssistantResponse("O modelo solicitou uma ferramenta desconhecida; nenhuma ação foi executada.")
            description = self._describe_tool_call(call)
            return AssistantResponse(
                f"A IA solicitou esta ação: {description}. Confirme para executá-la.",
                action="confirm_ai_tool", payload=call)
        return AssistantResponse(result.text or "O provedor não retornou texto. Tente reformular a solicitação.")

    def _provider(self, name: str):
        if self.provider_factory: return self.provider_factory(name)
        if name == "ollama":
            return OllamaProvider(self.settings.get("ollama_url"), self.settings.get("ollama_model"))
        if name == "openai": return OpenAIProvider(self.settings.get("openai_model"))
        raise RuntimeError("Provedor de IA inválido. Selecione Básico, Ollama ou OpenAI.")

    def provider_status(self) -> tuple[str, bool, str]:
        name = str(self.settings.get("ai_provider", "basic"))
        if name == "basic": return name, True, "modo básico — IA conversacional desativada"
        if name in self._last_provider_status: return name, *self._last_provider_status[name]
        try:
            provider = self._provider(name)
            if name == "ollama":
                ok = bool(provider.available())
                return name, ok, "conectado" if ok else "desconectado"
            ok, detail = provider.status()
            return name, bool(ok), str(detail)
        except Exception as exc:
            return name, False, str(exc)

    def execute_ai_tool(self, call: ToolCall) -> AssistantResponse:
        """Executa somente ferramentas registradas, depois da confirmação feita pela interface."""
        if call.name == "open_calculator":
            return self._run_tool("open_calculator", "Calculadora aberta.", lambda: windows.open_program("calculator"))
        if call.name == "open_notepad":
            return self._run_tool("open_notepad", "Bloco de Notas aberto.", lambda: windows.open_program("notepad"))
        if call.name == "open_browser":
            return self._run_tool("open_browser", "Navegador aberto.", windows.open_browser)
        if call.name == "show_tasks":
            tasks = self.db.tasks()
            return AssistantResponse("Nenhuma tarefa pendente." if not tasks else
                "Tarefas pendentes:\n" + "\n".join(f"• #{row['id']} {row['title']}" for row in tasks))
        if call.name == "list_memories":
            memories = self.db.memories()
            return AssistantResponse("Nenhuma memória cadastrada." if not memories else
                "Memórias autorizadas:\n" + "\n".join(f"• {row['content']}" for row in memories[:20]))
        if call.name == "organize_files":
            return AssistantResponse("Abra o organizador e revise a prévia antes de confirmar.", action="organize")
        if call.name == "find_files":
            return AssistantResponse("Escolha onde pesquisar.", action="find", payload=str(call.arguments.get("query", "")))
        if call.name == "open_directory":
            wanted = str(call.arguments.get("name", "")).casefold()
            matches = [p for p in self.settings.allowed_directories if wanted and wanted in p.name.casefold()]
            if not matches: return AssistantResponse("Essa pasta não está entre os diretórios autorizados.")
            return self._run_tool("open_directory", f"Pasta aberta: {matches[0]}", lambda: windows.open_directory(matches[0]))
        if call.name == "find_application":
            return self.request_application(str(call.arguments.get("query", "")))
        if call.name == "navigate_public_web":
            request = str(call.arguments.get("request", "")).strip()
            result = self.orchestrator.handle(request)
            return AssistantResponse(result.text if result.handled else "Pedido de navegacao nao reconhecido; nenhuma pagina foi aberta.", action="refresh_automations", payload=result.run_id)
        return AssistantResponse("Ferramenta não autorizada; nenhuma ação foi executada.")

    def request_application(self, query: str) -> AssistantResponse:
        matches = self.app_matcher.match(query)
        if not matches:
            action = "refresh_apps" if not self.db.applications() else "application_not_found"
            return AssistantResponse(f"Não encontrei um aplicativo instalado compatível com “{query}”.", action=action, payload=query)
        if len(matches) == 1 or (matches[0].score >= .82 and (len(matches) == 1 or matches[0].score-matches[1].score >= .12)):
            return AssistantResponse(f"Encontrei {matches[0].display_name}. Confirme antes de abrir.", action="confirm_application", payload=matches[0].app_id)
        return AssistantResponse("Encontrei mais de uma opção compatível. Escolha qual deseja abrir.", action="choose_application", payload=matches)

    def launch_application(self, app_id: str) -> AssistantResponse:
        success, message = self.app_launcher.launch(app_id)
        self.db.log_action("open_application", message, True, success)
        return AssistantResponse(message, action="refresh_app_view")

    def stop_automation(self) -> AssistantResponse:
        self.orchestrator.stop()
        run_id = self.orchestrator.current_run_id
        if run_id:
            self.db.finish_automation(run_id, "cancelado", "Interrompida pelo usuario.")
        return AssistantResponse("Automacao interrompida. Nenhuma nova etapa sera iniciada.", action="refresh_automations")

    def close(self) -> None:
        self.browser.close()

    @staticmethod
    def _application_query(text: str) -> str | None:
        match = re.search(r"\b(?:abra|abre|abrir|inicia|inicie|execute|executa)\s+(?:o |a )?(.+?)[.!?]*$", text, re.I)
        if match: return match.group(1).strip()
        low = normalize_app_name(text)
        if any(phrase in low for phrase in ("quero editar uma imagem", "preciso editar uma imagem", "preciso fazer um documento", "quero fazer uma planilha", "programa da minha impressora")):
            return text
        return None

    @staticmethod
    def _tool_descriptions() -> dict[str, str]:
        return {"open_calculator": "abrir a calculadora", "open_notepad": "abrir o Bloco de Notas",
                "open_browser": "abrir o navegador", "open_directory": "abrir uma pasta autorizada",
                "show_tasks": "consultar tarefas", "list_memories": "consultar memórias autorizadas",
                "organize_files": "abrir o organizador supervisionado", "find_files": "pesquisar arquivos",
                "find_application": "localizar um aplicativo instalado", "navigate_public_web": "navegar na web publica com supervisao"}

    def _describe_tool_call(self, call: ToolCall) -> str:
        description = self._tool_descriptions()[call.name]
        details = ", ".join(f"{key}={value}" for key, value in call.arguments.items())
        return f"{description} ({details})" if details else description

    @staticmethod
    def _instructions(memories: list[str], provider_name: str, intent: Intent) -> str:
        memory_text = "\n".join(f"- {item}" for item in memories) or "Nenhuma memória foi compartilhada."
        return (
            "Você é James, assistente pessoal profissional em português brasileiro. Seja educado, inteligente, objetivo e natural. "
            "Ajude na vida pessoal, serviços gráficos, administração de loja e Windows. Faça uma pergunta curta quando faltar contexto. "
            "Nunca diga que abriu, encontrou, moveu ou executou algo sem resultado real. Para ações disponíveis, use apenas as ferramentas estruturadas; "
            "não gere comandos de terminal e não trate uma sugestão como autorização. O aplicativo pedirá confirmação ao usuário. "
            f"O roteador local classificou a mensagem como {intent.value}; trate isso como pista, não como autorização. "
            f"Provedor atual: {provider_name}. Memórias autorizadas para este contexto:\n{memory_text}"
        )

    def _run_tool(self, permission: str, success_message: str, function) -> AssistantResponse:
        allowed, reason = self.policy.require_permission(permission)
        if not allowed:
            self.db.log_action(permission, reason, False, False)
            return AssistantResponse(reason)
        success, details = function()
        self.db.log_action(permission, details, True, success)
        return AssistantResponse(success_message if success else details)

    @staticmethod
    def help_text() -> str:
        return ("Comandos: abra a calculadora; abra o bloco de notas; abra o navegador; "
                "abra a pasta [nome]; informações do computador; adicione tarefa [texto]; mostre minhas tarefas; "
                "lembre que [informação]; o que você lembra; procure [arquivo]; organize os arquivos.")
